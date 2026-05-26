"""
Fairyland CLI — run the app from the command line.

Usage:
  fairyland                    # start on port 5000
  fairyland --port 8080        # custom port
  fairyland --host 0.0.0.0     # listen on all interfaces (LAN access)
"""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Fairyland — a non-extractive digital ecology"
    )
    parser.add_argument("--host", default="127.0.0.1",
                        help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000,
                        help="Port to listen on (default: 5000)")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug mode")
    parser.add_argument("--tattoo-dir", default=None,
                        help="Directory for tattoo persistence")

    args = parser.parse_args()

    if args.tattoo_dir:
        import os
        os.environ["FAIRYLAND_TATTOO_DIR"] = args.tattoo_dir

    from fairyland.app import create_app
    app = create_app()

    print(f"\n  Fairyland is running at http://{args.host}:{args.port}")
    if args.host == "0.0.0.0":
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            print(f"  Phone access: http://{local_ip}:{args.port}")
        except Exception:
            pass
    print()

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
