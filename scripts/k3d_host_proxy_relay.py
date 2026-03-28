from __future__ import annotations

import argparse
import socket
import socketserver
import sys
import threading


def _pump(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


class _RelayServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler_class: type[socketserver.BaseRequestHandler],
        *,
        upstream_host: str,
        upstream_port: int,
        connect_timeout_s: float,
    ) -> None:
        super().__init__(server_address, request_handler_class)
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.connect_timeout_s = connect_timeout_s


class _RelayHandler(socketserver.BaseRequestHandler):
    server: _RelayServer

    def handle(self) -> None:
        client = self.request
        try:
            upstream = socket.create_connection(
                (self.server.upstream_host, self.server.upstream_port),
                timeout=self.server.connect_timeout_s,
            )
        except OSError as exc:
            print(
                f"relay connect failed: {self.server.upstream_host}:{self.server.upstream_port} -> {exc}",
                file=sys.stderr,
                flush=True,
            )
            return

        t1 = threading.Thread(target=_pump, args=(client, upstream), daemon=True)
        t2 = threading.Thread(target=_pump, args=(upstream, client), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        try:
            upstream.close()
        finally:
            client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Expose a WSL-side TCP relay for local k3d pods.")
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=17897)
    parser.add_argument("--upstream-host", default="127.0.0.1")
    parser.add_argument("--upstream-port", type=int, default=7897)
    parser.add_argument("--connect-timeout-s", type=float, default=10.0)
    args = parser.parse_args(argv)

    server = _RelayServer(
        (args.listen_host, args.listen_port),
        _RelayHandler,
        upstream_host=args.upstream_host,
        upstream_port=args.upstream_port,
        connect_timeout_s=args.connect_timeout_s,
    )
    print(
        f"listening on {args.listen_host}:{args.listen_port} -> {args.upstream_host}:{args.upstream_port}",
        file=sys.stderr,
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 130
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
