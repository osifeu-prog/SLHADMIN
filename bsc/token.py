from web3 import Web3
from .client import get_w3, get_token_contract, require_chain

def token_meta() -> dict:
    w3 = get_w3()
    require_chain(w3)
    c = get_token_contract(w3)
    return {
        "address": c.address,
        "name": c.functions.name().call(),
        "symbol": c.functions.symbol().call(),
        "decimals": int(c.functions.decimals().call()),
        "totalSupply": str(c.functions.totalSupply().call()),
        "owner": c.functions.owner().call(),
        "paused": bool(c.functions.paused().call()),
    }

def balance_of(addr: str) -> dict:
    w3 = get_w3()
    require_chain(w3)
    c = get_token_contract(w3)
    a = Web3.to_checksum_address(addr)
    bal = int(c.functions.balanceOf(a).call())
    dec = int(c.functions.decimals().call())
    return {
        "address": a,
        "balance_raw": str(bal),
        "decimals": dec,
        "balance": bal / (10 ** dec),
    }