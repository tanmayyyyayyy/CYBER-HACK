"""Publish and check evidence commitments through an Ethereum JSON-RPC node."""

import json
import os
import re
from urllib.error import URLError
from urllib.request import Request, urlopen


PREFIX = "0x" + b"DRISHTI:MANIFEST:1:".hex()
TX_HASH = re.compile(r"0x[0-9a-fA-F]{64}")


class BlockchainError(Exception):
    pass


def rpc(method: str, *params):
    url = os.getenv("DRISHTI_CHAIN_RPC_URL")
    if not url:
        raise BlockchainError("Blockchain RPC is not configured.")
    try:
        request = Request(url, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=8) as response:
            result = json.load(response)
    except (URLError, OSError, ValueError) as exc:
        raise BlockchainError("Could not reach the configured blockchain node.") from exc
    if not isinstance(result, dict) or "result" not in result or "error" in result:
        raise BlockchainError(f"Blockchain node rejected {method}.")
    return result["result"]


def publish(digest: str) -> dict:
    chain_id = rpc("eth_chainId")
    demo = os.getenv("DRISHTI_CHAIN_DEMO") == "1"
    expected_chain_id = "0x7a69" if demo else os.getenv("DRISHTI_CHAIN_ID")
    if not expected_chain_id or chain_id != expected_chain_id:
        raise BlockchainError("The connected network does not match the configured chain ID.")
    sender = os.getenv("DRISHTI_CHAIN_SENDER")
    # Permit the demo account only when the operator explicitly enables demo mode.
    if not sender and demo and os.getenv("DRISHTI_CHAIN_RPC_URL") == "http://127.0.0.1:8545":
        sender = next(iter(rpc("eth_accounts")), None)
    if not sender or not re.fullmatch(r"0x[0-9a-fA-F]{40}", sender):
        raise BlockchainError("Configure an authorized blockchain sender account.")
    tx_hash = rpc("eth_sendTransaction", {"from": sender, "to": sender, "data": PREFIX + digest, "value": "0x0"})
    if not isinstance(tx_hash, str) or not TX_HASH.fullmatch(tx_hash):
        raise BlockchainError("Blockchain node did not return a transaction hash.")
    return {"chainId": chain_id, "transactionHash": tx_hash}


def verify(digest: str, chain_id: str, tx_hash: str) -> dict:
    if not TX_HASH.fullmatch(tx_hash):
        return {"verified": False, "reason": "Invalid transaction hash."}
    if rpc("eth_chainId") != chain_id:
        return {"verified": False, "reason": "The connected node is on a different chain."}
    tx = rpc("eth_getTransactionByHash", tx_hash)
    if not tx or tx.get("input", "").lower() != PREFIX + digest:
        return {"verified": False, "reason": "The transaction does not contain this manifest fingerprint."}
    receipt = rpc("eth_getTransactionReceipt", tx_hash)
    if not receipt:
        return {"verified": False, "reason": "Transaction is waiting to be included in a block."}
    if receipt.get("status") != "0x1":
        return {"verified": False, "reason": "Blockchain transaction failed."}
    block = rpc("eth_getBlockByNumber", receipt["blockNumber"], False)
    if not block or block.get("hash") != receipt.get("blockHash") or tx_hash.lower() not in [item.lower() for item in block.get("transactions", [])]:
        return {"verified": False, "reason": "Transaction is not in the current canonical block."}
    return {"verified": True, "blockNumber": int(receipt["blockNumber"], 16)}
