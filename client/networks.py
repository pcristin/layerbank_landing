from enum import Enum


class Network(Enum):
    ETHEREUM = {"chain_id": 1, "is_poa": False}
    OPTIMISM = {"chain_id": 10, "is_poa": False}
    BSC = {"chain_id": 56, "is_poa": True}
    POLYGON = {"chain_id": 137, "is_poa": False}
    ZKSYNC = {"chain_id": 324, "is_poa": False}
    MANTLE = {"chain_id": 5000, "is_poa": False}
    BASE = {"chain_id": 8453, "is_poa": False}
    ARBITRUM = {"chain_id": 42161, "is_poa": False}
    LINEA = {"chain_id": 59144, "is_poa": True}
    SCROLL = {"chain_id": 534352, "is_poa": False}
    CRONOS = {"chain_id": 25, "is_poa": True}
    ZKEVM = {"chain_id": 1101, "is_poa": False}
    CRONOS_ZKEVM = {"chain_id": 388, "is_poa": True}
    KUCOIN_CHAIN = {"chain_id": 321, "is_poa": True}
    ASTAR = {"chain_id": 592, "is_poa": False}
    KAIA = {"chain_id": 8217, "is_poa": True}
    NUMBERS = {"chain_id": 10507, "is_poa": True}
    BLAST = {"chain_id": 81457, "is_poa": False}
    X_LAYER = {"chain_id": 196, "is_poa": False}
    TAIKO = {"chain_id": 167, "is_poa": False}
    ABSTRACT = {"chain_id": 2741, "is_poa": True}
    BERACHAIN = {"chain_id": 8008, "is_poa": False}

    @property
    def chain_id(self) -> int:
        return self.value["chain_id"]

    @property
    def is_poa(self) -> bool:
        return self.value["is_poa"]

    @classmethod
    def from_chain_id(cls, chain_id: int) -> 'Network':
        for network in cls:
            if network.chain_id == chain_id:
                return network
        raise ValueError(f"Неизвестный chain_id: {chain_id}")

    @classmethod
    def from_name(cls, name: str) -> 'Network':
        try:
            return cls[name.upper()]
        except KeyError:
            raise ValueError(f"Неизвестная сеть: {name}. Поддерживаемые сети: {[n.name for n in cls]}")
