import json
import os
from pathlib import Path
from web3 import Web3

def _must(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env: {name}")
    return v

def get_w3() -> Web3:
    rpc = _must("BSC_RPC_URL")
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 20}))
    if not w3.is_connected():
        raise RuntimeError("BSC RPC not reachable")
    return w3

def get_token_contract(w3: Web3):
    addr = Web3.to_checksum_address(_must("BSC_TOKEN_ADDRESS"))
    abi_path = Path(_must("BSC_ABI_PATH"))
    abi = json.loads(abi_path.read_text(encoding="utf-8"))
    return w3.eth.contract(address=addr, abi=abi)

def require_chain(w3: Web3):
    expected = int(_must("BSC_CHAIN_ID"))
    chain_id = int(w3.eth.chain_id)
    if chain_id != expected:
        raise RuntimeError(f"Wrong chain_id: got {chain_id}, expected {expected}")