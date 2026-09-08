import sys
import os
import multiprocessing
import uvicorn

SERVICES = [
    ("services.user_service.main:app", 8001),
    ("services.order_service.main:app", 8002),
    ("services.payment_service.main:app", 8003),
    ("services.notification_service.main:app", 8004),
]

def _run(app_str: str, port: int, root_dir: str):
    import sys
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
    uvicorn.run(app_str, host="0.0.0.0", port=port, log_level="warning")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    processes = []
    for app_str, port in SERVICES:
        p = multiprocessing.Process(target=_run, args=(app_str, port, root), daemon=True)
        p.start()
        processes.append(p)
    print("Started 4 microservices on ports 8001-8004", flush=True)
    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        for p in processes:
            p.terminate()
