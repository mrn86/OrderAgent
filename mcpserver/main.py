"""启动 MCP Streamable HTTP 服务（默认 127.0.0.1:8010/mcp）。"""

from __future__ import annotations

import argparse
import os

import path_setup  # noqa: F401

from server import mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="order-agent MCP server")
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", "8010")))
    parser.add_argument("--path", default=os.getenv("MCP_PATH", "/mcp"))
    args = parser.parse_args()

    mcp.run(
        transport="streamable-http",
        host=args.host,
        port=args.port,
        streamable_http_path=args.path,
        stateless_http=True,
        json_response=True,
    )


if __name__ == "__main__":
    main()
