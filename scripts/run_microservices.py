"""Run the four in-memory demo APIs locally, without opening the saved app database.

Example: python scripts/run_microservices.py --base-port 8001
The demo APIs bind to loopback by default and are not a production service fleet.
"""
import argparse
import multiprocessing
import os
from pathlib import Path
import socket
import sys
import time
import urllib.error
import urllib.request
import json

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts._runtime import ROOT, ensure_runtime

SERVICE_NAMES = ("user", "order", "payment", "notification")
SERVICES = [(f"services.{name}_service.main:app", 8001 + index) for index, name in enumerate(SERVICE_NAMES)]


def _run(app_str, port, root_dir, host, urls):
    import uvicorn
    sys.path.insert(0, root_dir)
    os.environ.update(urls)
    uvicorn.run(app_str, host=host, port=port, log_level="warning")


def check_ports(host, ports):
    reserved = []
    try:
        for port in ports:
            listener = socket.socket()
            try:
                if os.name == "nt":
                    listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                listener.bind((host, port))
            except OSError:
                listener.close()
                raise SystemExit(f"Port {port} is already in use or unavailable. Stop that service yourself or select --base-port with four free ports.") from None
            reserved.append(listener)
    finally:
        for listener in reserved:
            listener.close()


def wait_ready(processes, host, ports, timeout):
    deadline = time.monotonic() + timeout
    pending = set(ports)
    address = "127.0.0.1" if host == "0.0.0.0" else host
    while pending and time.monotonic() < deadline:
        for process in processes:
            if process.exitcode is not None:
                raise RuntimeError(f"A service exited during startup (exit code {process.exitcode})")
        for port in list(pending):
            try:
                with urllib.request.urlopen(f"http://{address}:{port}/health", timeout=.3) as response:
                    if response.status == 200:
                        pending.remove(port)
            except OSError:
                pass
        if pending:
            time.sleep(.1)
    if pending:
        raise RuntimeError("Service startup timed out on ports: " + ", ".join(map(str, sorted(pending))))


def stop_processes(processes):
    for process in processes:
        if process.is_alive():
            process.terminate()
    for process in processes:
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join(timeout=5)


def exercise_services(ports):
    def request(index, path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{ports[index]}" + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read())
    for index, path, body in ((1, "/orders", {"user_id": "missing-user", "items": []}),
                              (2, "/payments", {"order_id": -1, "amount": 1, "method": "test"})):
        try:
            request(index, path, body)
        except urllib.error.HTTPError as error:
            if error.code != 400:
                raise RuntimeError("Inter-service validation returned an unexpected status") from None
        else:
            raise RuntimeError("A demo service failed to validate its upstream dependency")
    user = request(0, "/users", {"name": "Disposable launcher test", "email": "launcher@example.com"})
    order = request(1, "/orders", {"user_id": user["id"], "items": [{"product_id": "test", "quantity": 1, "price": 10}]})
    payment = request(2, "/payments", {"order_id": order["id"], "amount": order["total"], "method": "test"})
    notices = request(3, "/notifications?user_id=" + user["id"])
    if payment["status"] != "completed" or not notices:
        raise RuntimeError("The demo order/payment/notification flow did not complete")
    print("User, order, payment and notification connections passed (disposable in-memory data).", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-port", type=int, default=8001)
    parser.add_argument("--host", choices=("127.0.0.1", "0.0.0.0"), default="127.0.0.1")
    parser.add_argument("--startup-timeout", type=float, default=30)
    parser.add_argument("--check", action="store_true", help="Start, health-check, exercise inter-service calls, then stop only these temporary processes")
    args = parser.parse_args(argv)
    if not 1 <= args.base_port <= 65532:
        parser.error("--base-port must leave room for four ports between 1 and 65535")
    if args.startup_timeout <= 0:
        parser.error("--startup-timeout must be positive")
    ensure_runtime(("uvicorn", "fastapi", "httpx", "email_validator"), "-r services/requirements-local.txt")
    ports = list(range(args.base_port, args.base_port + 4))
    check_ports(args.host, ports)
    urls = {name.upper() + "_SERVICE_URL": f"http://127.0.0.1:{port}" for name, port in zip(SERVICE_NAMES, ports)}
    processes = []
    try:
        for (app_str, _), port in zip(SERVICES, ports):
            process = multiprocessing.get_context("spawn").Process(
                target=_run, args=(app_str, port, str(ROOT), args.host, urls))
            process.start()
            processes.append(process)
        wait_ready(processes, args.host, ports, args.startup_timeout)
        print("All four demo services are healthy on ports " + ", ".join(map(str, ports)), flush=True)
        if args.check:
            exercise_services(ports)
            return 0
        while True:
            for process in processes:
                if process.exitcode is not None:
                    raise RuntimeError(f"A demo service stopped (exit code {process.exitcode})")
            time.sleep(.2)
    except KeyboardInterrupt:
        return 0
    except (OSError, RuntimeError) as error:
        print(f"Service launcher failed: {error}", file=sys.stderr)
        return 1
    finally:
        stop_processes(processes)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
