from functools import wraps
from aiohttp import ClientHttpProxyError
from eth_account import Account
from web3.middleware.geth_poa import async_geth_poa_middleware
from web3.exceptions import TransactionNotFound
from web3 import AsyncWeb3, AsyncHTTPProvider
from web3.contract import AsyncContract
from typing import Optional, Union
from web3.types import TxParams
from hexbytes import HexBytes
from client.networks import Network
import asyncio
import logging
import json

with open("abi/erc20_abi.json", "r", encoding="utf-8") as file:
    ERC20_ABI = json.load(file)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)


def retry_on_proxy_error(max_attempts: int = 3, fallback_no_proxy: bool = True):
    """Декоратор для повторных попыток при ошибках прокси."""

    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            attempts = 0
            last_error = None
            while attempts < max_attempts:
                try:
                    return await func(self, *args, **kwargs)
                except ClientHttpProxyError as e:
                    attempts += 1
                    last_error = e
                    logger.warning(f"🧹 Ошибка прокси (попытка {attempts}/{max_attempts}): {e}")
                    if attempts == max_attempts and fallback_no_proxy:
                        logger.info("Отключаем прокси для последней попытки")
                        self._disable_proxy()
                        try:
                            return await func(self, *args, **kwargs)
                        except ClientHttpProxyError as e:
                            last_error = e
                    await asyncio.sleep(1)
            raise ValueError(f"❌ Не удалось выполнить запрос после {max_attempts} попыток: {last_error}")

        return wrapper

    return decorator


class Client:
    def __init__(self, ltoken_address: str, core_address: str, chain_id: int, rpc_url: str, private_key: str,
                 amount: float, explorer_url: str, usdc_address: str, proxy: Optional[str] = None):
        request_kwargs = {"proxy": f"http://{proxy}"} if proxy else {}
        self.ltoken_address = ltoken_address
        self.explorer_url = explorer_url
        self.private_key = private_key
        self.account = Account.from_key(self.private_key)
        self.core_address = core_address
        self.usdc_address = usdc_address
        self.chain_id = chain_id
        self.amount = amount
        self.rpc_url = rpc_url
        self.proxy = proxy

        # Определяем сеть
        if isinstance(chain_id, str):
            self.network = Network.from_name(chain_id)
        else:
            self.network = Network.from_chain_id(chain_id)

        self.chain_id = self.network.chain_id

        # Инициализация AsyncWeb3
        self.w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url, request_kwargs=request_kwargs))
        # Применяем middleware для PoA-сетей
        if self.network.is_poa:
            self.w3.middleware_onion.clear()
            self.w3.middleware_onion.inject(async_geth_poa_middleware, layer=0)

        self.eip_1559 = True
        self.address = self.w3.to_checksum_address(
            self.w3.eth.account.from_key(self.private_key).address)

    # Получение баланса нативного токена
    async def get_native_balance(self) -> float:
        """Получает баланс нативного токена в ETH/BNB/MATIC и т.д."""
        balance_wei = await self.w3.eth.get_balance(self.address)
        return balance_wei

    async def get_allowance(self, token_address: str, owner: str, spender: str) -> int:
        try:
            contract = await self.get_contract(token_address, ERC20_ABI)
            allowance = await contract.functions.allowance(
                self.w3.to_checksum_address(owner),
                self.w3.to_checksum_address(spender)
            ).call()
            return allowance
        except Exception as e:
            logger.error(f"❌ Ошибка при получении allowance: {e}")
            return 0

    # Врап нативного токена
    async def wrap_native(self, token_address: str, amount_wei: int = None) -> str:
        """
        Оборачивает нативный токен (ETH/BNB/MATIC) в WETH/WBNB/WMATIC.
        """
        from utils.wrappers import wrap_native_token
        if amount_wei is None:
            amount_wei = self.to_wei_main(self.amount, token_address)

        tx = await wrap_native_token(self.w3, self.network.name, amount_wei, self.address)
        signed = self.w3.eth.account.sign_transaction(tx, self.private_key)
        tx_hash = await self.w3.eth.send_raw_transaction(signed.raw_transaction)
        logger.info(f"🚀 Отправлен wrap-тx: {tx_hash.hex()}\n")
        return tx_hash.hex()

    # Анврап нативного токена
    async def unwrap_native(self, amount_wei: int) -> str:
        """
        Разворачивает WETH/WBNB/... обратно в нативный токен.
        """
        from utils.wrappers import unwrap_native_token
        tx = await unwrap_native_token(self.w3, self.network.name, amount_wei, self.address)
        signed = self.w3.eth.account.sign_transaction(tx, self.private_key)
        tx_hash = await self.w3.eth.send_raw_transaction(signed.raw_transaction)
        logger.info(f"🚀 Отправлен unwrap-тx: {tx_hash.hex()}\n")
        return tx_hash.hex()

    # Получение баланса ERC20
    async def get_erc20_balance(self) -> float | int:

        contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(self.usdc_address), abi=ERC20_ABI)
        try:
            balance = await contract.functions.balanceOf(self.address).call()
            return balance
        except Exception as e:
            logger.error(f"❌ Ошибка при получении баланса ERC20: {e}")
            return 0

    # Создание объекта контракт для дальнейшего обращения к нему
    async def get_contract(self, contract_address: str, abi: list) -> AsyncContract:
        return self.w3.eth.contract(
            address=self.w3.to_checksum_address(contract_address), abi=abi
        )

    # Получение суммы газа за транзакцию
    async def get_tx_fee(self) -> int:
        try:
            fee_history = await self.w3.eth.fee_history(10, "latest", [50])
            base_fee = fee_history['baseFeePerGas'][-1]
            max_priority_fee = await self.w3.eth.max_priority_fee
            estimated_gas = 70_000
            max_fee_per_gas = (base_fee + max_priority_fee) * estimated_gas

            return max_fee_per_gas
        except Exception as e:
            logger.warning(f"Ошибка при расчёте комиссии, используем fallback: {e}")
            fallback_gas_price = await self.w3.eth.gas_price
            return fallback_gas_price * 70_000

    # Преобразование в веи
    async def to_wei_main(self, number: int | float, token_address: Optional[str] = None):
        if token_address:
            contract = await self.get_contract(token_address, ERC20_ABI)
            decimals = await contract.functions.decimals().call()
        else:
            decimals = 18

        unit_name = {
            6: "mwei",
            9: "gwei",
            18: "ether"
        }.get(decimals)

        if not unit_name:
            raise RuntimeError(f"Невозможно найти имя юнита с децималами: {decimals}")
        return self.w3.to_wei(number, unit_name)

    # Преобразование из веи
    async def from_wei_main(self, number: int | float, token_address: Optional[str] = None):
        if token_address:
            contract = await self.get_contract(token_address, ERC20_ABI)
            decimals = await contract.functions.decimals().call()
        else:
            decimals = 18

        unit_name = {
            6: "mwei",
            9: "gwei",
            18: "ether"
        }.get(decimals)

        if not unit_name:
            raise RuntimeError(f"Невозможно найти имя юнита с децималами: {decimals}")
        return self.w3.from_wei(number, unit_name)

    # Метод для построения транзакции
    async def prepare_tx(self, value: Union[int, float] = 0) -> TxParams:
        """Подготавливает базовую транзакцию."""
        try:
            nonce = await self.w3.eth.get_transaction_count(self.address)
            chain_id = await self.w3.eth.chain_id
            
            tx_params = {
                'from': self.address,
                'nonce': nonce,
                'chainId': chain_id,
            }
            
            if value > 0:
                tx_params['value'] = value
                
            # Добавляем параметры EIP-1559 если поддерживается
            if self.eip_1559:
                base_fee = await self.w3.eth.gas_price
                max_priority_fee = int(base_fee * 0.1) or 1_000_000  # Минимальная чаевая
                max_fee = int(base_fee * 1.5 + max_priority_fee)
                
                tx_params.update({
                    'maxFeePerGas': max_fee,
                    'maxPriorityFeePerGas': max_priority_fee
                })
            else:
                tx_params['gasPrice'] = await self.w3.eth.gas_price
                
            return tx_params
        except Exception as e:
            logger.error(f"Ошибка при подготовке транзакции: {e}")
            raise

    # Метод для подписи и отправки транзакции
    async def sign_and_send_tx(self, transaction: TxParams, without_gas: bool = False) -> str:
        """Подписывает и отправляет транзакцию."""
        try:
            if not without_gas:
                # Оцениваем газ, если не указан
                if 'gas' not in transaction:
                    try:
                        tx_copy = dict(transaction)
                        del tx_copy['gasPrice']  # Удаляем для совместимости с estimateGas
                        gas_estimate = await self.w3.eth.estimate_gas(tx_copy)
                        transaction['gas'] = int(gas_estimate * 1.2)  # Добавляем 20% запас
                    except Exception as e:
                        logger.warning(f"Не удалось оценить газ: {e}. Используем фиксированное значение.")
                        transaction['gas'] = 300000  # Фолбек на фиксированный газ
            
            signed_tx = self.w3.eth.account.sign_transaction(transaction, self.private_key)
            tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            return tx_hash.hex()
        except Exception as e:
            logger.error(f"Ошибка при подписи или отправке транзакции: {e}")
            raise

    # Метод для ожидания завершения транзакции
    async def wait_tx(self, tx_hash: Union[str, HexBytes], explorer_url: Optional[str] = None) -> bool:
        """
        Ожидает завершения транзакции и возвращает статус успеха.
        """
        if isinstance(tx_hash, str):
            tx_hash = HexBytes(tx_hash)
        
        if explorer_url and not explorer_url.endswith('/'):
            explorer_url += '/'
        
        tx_url = f"{explorer_url}tx/{tx_hash.hex()}" if explorer_url else f"Хэш транзакции: {tx_hash.hex()}"
        logger.info(f"⏳ Ожидание подтверждения транзакции: {tx_url}\n")
        
        max_attempts = 50
        for attempt in range(max_attempts):
            try:
                receipt = await self.w3.eth.get_transaction_receipt(tx_hash)
                if receipt is not None:
                    if receipt['status'] == 1:
                        logger.info(f"✅ Транзакция успешно подтверждена! Блок: {receipt['blockNumber']}\n")
                        return True
                    else:
                        logger.error(f"❌ Транзакция не удалась. Подробности: {tx_url}\n")
                        return False
            except TransactionNotFound:
                pass  # Транзакция еще не включена в блок
            except Exception as e:
                logger.error(f"Ошибка при проверке статуса транзакции: {e}")
                # Продолжаем ожидание
            
            await asyncio.sleep(5)
        
        logger.warning(f"⚠️ Превышено время ожидания подтверждения транзакции: {tx_url}\n")
        return False

    # Метод для отправки approve-транзакции
    async def approve_usdc(self, usdc_contract, spender, amount):
        """Отправляет транзакцию для аппрува токена."""
        try:
            logger.info(f"🔑 Подготовка транзакции аппрува USDC на сумму {await self.from_wei_main(amount, self.usdc_address):.6f}")
            
            # Подготовка транзакции
            tx_params = await self.prepare_tx()
            tx = await usdc_contract.functions.approve(spender, amount).build_transaction(tx_params)
            
            # Подпись и отправка
            tx_hash = await self.sign_and_send_tx(tx)
            logger.info(f"📝 Транзакция аппрува отправлена: {tx_hash}")
            
            success = await self.wait_tx(tx_hash, self.explorer_url)
            if success:
                logger.info(f"✅ Транзакция аппрува успешно подтверждена!")
                
                # Проверяем, что аппрув действительно установлен
                try:
                    new_allowance = await self.get_allowance(self.usdc_address, self.address, spender)
                    if new_allowance >= amount:
                        logger.info(f"✅ Аппрув успешно установлен. Разрешено: {await self.from_wei_main(new_allowance, self.usdc_address):.6f}\n")
                        return True
                    else:
                        logger.warning(f"⚠️ Аппрув подтвержден, но allowance меньше требуемого: {await self.from_wei_main(new_allowance, self.usdc_address):.6f} < {await self.from_wei_main(amount, self.usdc_address):.6f}\n")
                        return False
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось проверить новый allowance: {e}\n")
                    return True  # Предполагаем успех, так как транзакция прошла
            else:
                logger.error(f"❌ Не удалось выполнить аппрув USDC\n")
                return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка при выполнении аппрува: {e}")
            raise

    # Метод для построения swap транзакции
    async def build_swap_tx(self, quote_data: dict) -> TxParams:
        """
        Строим транзакцию для обмена токенов, используя котировку.
        """
        raise NotImplementedError("Эта функция не используется в данном проекте")
