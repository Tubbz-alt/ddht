import ipaddress
from typing import Any, Callable, List, Mapping, NamedTuple, Tuple, Union

from eth_utils import add_0x_prefix, encode_hex, remove_0x_prefix

try:
    import web3  # noqa: F401
except ImportError:
    raise ImportError("The web3.py library is required")


from eth_enr import ENR, ENRAPI
from eth_typing import HexStr, NodeID
from eth_utils import decode_hex
from web3.method import Method
from web3.module import ModuleV2
from web3.types import RPCEndpoint

from ddht.rpc_handlers import BucketInfo as BucketInfoDict
from ddht.rpc_handlers import NodeInfoResponse, TableInfoResponse
from ddht.typing import AnyIPAddress
from ddht.v5_1.rpc_handlers import PongResponse


class NodeInfo(NamedTuple):
    node_id: NodeID
    enr: ENRAPI

    @classmethod
    def from_rpc_response(cls, response: NodeInfoResponse) -> "NodeInfo":
        return cls(
            node_id=NodeID(decode_hex(response["node_id"])),
            enr=ENR.from_repr(response["enr"]),
        )


class BucketInfo(NamedTuple):
    idx: int
    nodes: Tuple[NodeID, ...]
    replacement_cache: Tuple[NodeID, ...]
    is_full: bool

    @classmethod
    def from_rpc_response(cls, response: BucketInfoDict) -> "BucketInfo":
        return cls(
            idx=response["idx"],
            nodes=tuple(
                NodeID(decode_hex(node_id_hex)) for node_id_hex in response["nodes"]
            ),
            replacement_cache=tuple(
                NodeID(decode_hex(node_id_hex))
                for node_id_hex in response["replacement_cache"]
            ),
            is_full=response["is_full"],
        )


class TableInfo(NamedTuple):
    center_node_id: NodeID
    num_buckets: int
    bucket_size: int
    buckets: Mapping[int, BucketInfo]

    @classmethod
    def from_rpc_response(cls, response: TableInfoResponse) -> "TableInfo":
        return cls(
            center_node_id=NodeID(decode_hex(response["center_node_id"])),
            num_buckets=response["num_buckets"],
            bucket_size=response["bucket_size"],
            buckets={
                int(idx): BucketInfo.from_rpc_response(bucket_stats)
                for idx, bucket_stats in response["buckets"].items()
            },
        )


class PongPayload(NamedTuple):
    enr_seq: int
    packet_ip: AnyIPAddress
    packet_port: int

    @classmethod
    def from_rpc_response(cls, response: PongResponse) -> "PongPayload":
        return cls(
            enr_seq=response["enr_seq"],
            packet_ip=ipaddress.ip_address(response["packet_ip"]),
            packet_port=response["packet_port"],
        )


class RPC:
    nodeInfo = RPCEndpoint("discv5_nodeInfo")
    routingTableInfo = RPCEndpoint("discv5_routingTableInfo")

    ping = RPCEndpoint("discv5_ping")


def ping_munger(
    module: Any, identifier: Union[ENRAPI, str, bytes, NodeID, HexStr]
) -> List[str]:
    """
    See: https://github.com/ethereum/web3.py/blob/002151020cecd826a694ded2fdc10cc70e73e636/web3/method.py#L77  # noqa: E501

    Normalizes the any of the following inputs into the appropriate payload for
    the ``discv5_ping` JSON-RPC API endpoint.

    - An ENR object
    - The string representation of an ENR
    - A NodeID in the form of a bytestring
    - A NodeID in the form of a hex string
    - An ENode URI

    Throws a ``ValueError`` if the input cannot be matched to one of these
    formats.
    """
    if isinstance(identifier, ENRAPI):
        return [repr(identifier)]
    elif isinstance(identifier, bytes):
        if len(identifier) == 32:
            return [encode_hex(identifier)]
        raise ValueError(f"Unrecognized node identifier: {identifier!r}")
    elif isinstance(identifier, str):
        if identifier.startswith("enode://") or identifier.startswith("enr:"):
            return [identifier]
        elif len(remove_0x_prefix(HexStr(identifier))) == 64:
            return [add_0x_prefix(HexStr(identifier))]
        else:
            raise ValueError(f"Unrecognized node identifier: {identifier}")
    else:
        raise ValueError(f"Unrecognized node identifier: {identifier}")


# TODO: why does mypy think ModuleV2 is of `Any` type?
class DiscoveryV5Module(ModuleV2):  # type: ignore
    """
    A web3.py module that exposes high level APIs for interacting with the
    discovery v5 network.
    """

    get_node_info: Method[Callable[[], NodeInfo]] = Method(
        RPC.nodeInfo, result_formatters=lambda method: NodeInfo.from_rpc_response,
    )
    get_routing_table_info: Method[Callable[[], TableInfo]] = Method(
        RPC.routingTableInfo,
        result_formatters=lambda method: TableInfo.from_rpc_response,
    )

    ping: Method[Callable[[Union[NodeID, ENRAPI, HexStr, str]], PongPayload]] = Method(
        RPC.ping,
        result_formatters=lambda method: PongPayload.from_rpc_response,
        mungers=[ping_munger],
    )
