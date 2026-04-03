import os, json
from web3 import Web3

rpc = os.getenv("BSC_RPC_URL") or "https://bsc-dataseed.binance.org/"
token = os.getenv("BSC_TOKEN_ADDRESS")
abi_path = os.getenv("BSC_ABI_PATH") or "bsc/abi/FullFeatureToken.json"
addr = os.getenv("ADDR_USER")

if not token:
    raise SystemExit("Missing BSC_TOKEN_ADDRESS")
if not os.path.exists(abi_path):
    raise SystemExit(f"Missing ABI file at {abi_path}")

w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 20}))
if not w3.is_connected():
    raise SystemExit("RPC not reachable")

abi = json.load(open(abi_path, "r", encoding="utf-8"))
c = w3.eth.contract(address=Web3.to_checksum_address(token), abi=abi)

name = c.functions.name().call()
sym  = c.functions.symbol().call()
dec  = c.functions.decimals().call()
total = c.functions.totalSupply().call()

print("name:", name)
print("symbol:", sym)
print("decimals:", dec)
print("totalSupply(raw):", total)

if addr:
    bal = c.functions.balanceOf(Web3.to_checksum_address(addr)).call()
    print("balanceOf(raw):", bal)
    print("balanceOf:", bal / (10**dec))
