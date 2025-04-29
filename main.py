from eth_utils import to_checksum_address
from config.configvalidator import ConfigValidator
from client.client import Client
from utils.logger import logger
import asyncio
import json
import sys

# Load ABI files
try:
    with open("abi/core_abi.json", "r", encoding="utf-8") as f:
        CORE_ABI = json.load(f)

    with open("abi/erc20_abi.json", "r", encoding="utf-8") as f:
        ERC20_ABI = json.load(f)
except FileNotFoundError as e:
    logger.error(f"Ошибка при загрузке ABI файлов: {e}")
    sys.exit(1)
except json.JSONDecodeError as e:
    logger.error(f"Ошибка при парсинге ABI файлов: {e}")
    sys.exit(1)


async def main():
    try:
        logger.info("🚀 Запуск скрипта...\n")
        # Загрузка параметров
        logger.info("⚙️ Загрузка и валидация параметров...\n")
        validator = ConfigValidator("config/settings.json")
        settings = await validator.validate_config()

        try:
            with open("constants/networks_data.json", "r", encoding="utf-8") as file:
                networks_data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка при загрузке данных сетей: {e}")
            sys.exit(1)

        if settings["network"] not in networks_data:
            logger.error(f"Сеть {settings['network']} не найдена в файле данных сетей")
            sys.exit(1)

        network = networks_data[settings["network"]]

        client = Client(
            proxy=settings["proxy"],
            rpc_url=network["rpc_url"],
            chain_id=network["chain_id"],
            amount=float(settings["amount"]),
            private_key=settings["private_key"],
            explorer_url=network["explorer_url"],
            usdc_address=to_checksum_address(network["usdc_address"]),
            core_address=to_checksum_address(network["core_address"]),
            ltoken_address=to_checksum_address(network["ltoken_address"])
        )

        # Проверка баланса
        amount_in = await client.to_wei_main(client.amount, client.usdc_address)
        erc20_balance = await client.get_erc20_balance()
        native_balance = await client.get_native_balance()
        gas = await client.get_tx_fee()
        
        logger.info(f"💰 Баланс USDC: {await client.from_wei_main(erc20_balance, client.usdc_address):.6f}")
        logger.info(f"⛽ Расчетная стоимость газа: {await client.from_wei_main(gas):.8f}\n")
        
        if amount_in > erc20_balance:
            logger.error(f"Недостаточно баланса USDC! Требуется: {await client.from_wei_main(amount_in, client.usdc_address):.6f}"
                         f" фактический баланс: {await client.from_wei_main(erc20_balance, client.usdc_address):.6f}\n")
            sys.exit(1)
        if native_balance < gas:
            logger.error(f"Недостаточно средств для оплаты газа! Требуется: {await client.from_wei_main(gas):.8f}"
                         f" фактический баланс: {await client.from_wei_main(native_balance):.8f}\n")
            sys.exit(1)

        # Аппрув токена и обращение к контракту
        usdc_contract = await client.get_contract(to_checksum_address(client.usdc_address), abi=ERC20_ABI)

        # Проверяем текущий allowance
        current_allowance = await client.get_allowance(client.usdc_address, client.address, client.ltoken_address)
        if current_allowance < amount_in:
            logger.info(f"💸 Требуется аппрув USDC на сумму {await client.from_wei_main(amount_in, client.usdc_address):.6f}\n")
            await client.approve_usdc(usdc_contract, client.ltoken_address, amount_in)
        else:
            logger.info(f"✅ Аппрув уже установлен, пропускаем этап аппрува\n")

        core = await client.get_contract(to_checksum_address(client.core_address), abi=CORE_ABI)

        logger.info("⚙️ Собираем и подписываем транзакцию размещения...\n")
        try:
            tx = await core.functions.supply(client.ltoken_address, amount_in).build_transaction(
                await client.prepare_tx())

            tx_hash = await client.sign_and_send_tx(tx)
            logger.info(f"📝 Транзакция отправлена: {tx_hash}\n")

            success = await client.wait_tx(tx_hash, client.explorer_url)
            if success:
                logger.info(f"✅ USDC успешно размещены на LayerBank! Сумма: {await client.from_wei_main(amount_in, client.usdc_address):.6f}\n")
                
                # Проверяем обновленный баланс lToken
                try:
                    ltoken_contract = await client.get_contract(client.ltoken_address, ERC20_ABI)
                    ltoken_balance = await ltoken_contract.functions.balanceOf(client.address).call()
                    logger.info(f"🏦 Ваш баланс lUSDC: {await client.from_wei_main(ltoken_balance, client.ltoken_address):.6f}\n")
                except Exception as e:
                    logger.warning(f"Не удалось получить баланс lUSDC: {e}\n")
            else:
                logger.error(f"❌ Не удалось разместить USDC на LayerBank\n")
        except Exception as e:
            logger.error(f"❌ Ошибка при размещении USDC: {e}\n")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Произошла ошибка в основном пути: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
