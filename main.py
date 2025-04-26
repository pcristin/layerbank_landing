from eth_utils import to_checksum_address
from config.configvalidator import ConfigValidator
from client.client import Client
from utils.logger import logger
import asyncio
import json

with open("abi/core_abi.json", "r", encoding="utf-8") as f:
    CORE_ABI = json.load(f)

with open("abi/erc20_abi.json", "r", encoding="utf-8") as f:
    ERC20_ABI = json.load(f)


async def main():
    try:
        logger.info("🚀 Запуск скрипта...\n")
        # Загрузка параметров
        logger.info("⚙️ Загрузка и валидация параметров...\n")
        validator = ConfigValidator("config/settings.json")
        settings = await validator.validate_config()

        with open("constants/networks_data.json", "r", encoding="utf-8") as file:
            networks_data = json.load(file)

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
        if amount_in > erc20_balance:
            logger.error(f"Недостаточно баланса USDC! Требуется: {await client.from_wei_main(amount_in):.6f}"
                         f" фактический баланс: {await client.from_wei_main(erc20_balance):.6f}\n")
            exit(1)
        if native_balance < gas:
            logger.error(f"Недостаточно средств для оплаты газа! Требуется: {await client.from_wei_main(gas):.8f}"
                         f" фактический баланс: {await client.from_wei_main(native_balance):.8f}\n")
            exit(1)

        # Аппрув токена и обращение к контракту
        usdc_contract = await client.get_contract(to_checksum_address(client.usdc_address), abi=ERC20_ABI)

        await client.approve_usdc(usdc_contract, client.ltoken_address, amount_in)

        core = await client.get_contract(to_checksum_address(client.core_address), abi=CORE_ABI)

        logger.info("⚙️ Собираем и подписываем транзакцию...\n")
        tx = await core.functions.supply(client.ltoken_address, amount_in).build_transaction(
            await client.prepare_tx(amount_in))

        tx_hash = await client.sign_and_send_tx(tx)

        await client.wait_tx(tx_hash, client.explorer_url)

    except Exception as e:
        logger.error(f"Произошла ошибка в основном пути: {e}")


if __name__ == "__main__":
    asyncio.run(main())
