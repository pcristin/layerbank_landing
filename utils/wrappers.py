from eth_typing import ChecksumAddress
from web3 import AsyncWeb3

WRAPPED_NATIVE_ADDRESSES = {
    "Optimism": "0x4200000000000000000000000000000000000006",  # WETH
    "BSC": "0xBB4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",       # WBNB
    "Polygon": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",   # WMATIC
    "ARBITRUM": "0x82af49447d8a07e3bd95bd0d56f35241523fbab1"  # WETH
}

WETH_ABI = [
    {
        "constant": False,
        "inputs": [],
        "name": "deposit",
        "outputs": [],
        "payable": True,
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [{"name": "wad", "type": "uint256"}],
        "name": "withdraw",
        "outputs": [],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function"
    }
]


async def wrap_native_token(w3: AsyncWeb3, network: str, amount_wei: int, wallet_address: ChecksumAddress):
    """Оборачивает нативный токен в WETH/WBNB/..."""
    token_address = WRAPPED_NATIVE_ADDRESSES[network.upper()]
    token_address = AsyncWeb3.to_checksum_address(token_address)
    contract = w3.eth.contract(address=token_address, abi=WETH_ABI)
    gas_estimate = await contract.functions.deposit().estimate_gas({
        "from": wallet_address,
        "value": amount_wei,
    })
    tx = await contract.functions.deposit().build_transaction({
        "from": wallet_address,
        "value": amount_wei,
        "nonce": await w3.eth.get_transaction_count(wallet_address),
        "gas": int(gas_estimate * 1.2),
        "gasPrice": await w3.eth.gas_price
    })
    return tx


async def unwrap_native_token(w3: AsyncWeb3, network: str, amount_wei: int, wallet_address: ChecksumAddress):
    """Разворачивает WETH/WBNB/... обратно в нативный токен"""
    token_address = WRAPPED_NATIVE_ADDRESSES[network.upper()]
    token_address = AsyncWeb3.to_checksum_address(token_address)
    contract = w3.eth.contract(address=token_address, abi=WETH_ABI)
    tx = await contract.functions.withdraw(amount_wei).build_transaction({
        "from": wallet_address,
        "nonce": await w3.eth.get_transaction_count(wallet_address),
        "gas": 100_000,
        "gasPrice": await w3.eth.gas_price
    })
    return tx
