import json
import sys

from . import client


def main(argv: list[str] | None = None) -> int:
    parser = client.build_parser()
    args = parser.parse_args(argv)
    queue_meta = None
    operation = getattr(args, "operation", "unknown")
    diagnostics = client.build_client_diagnostics(operation=operation)
    try:
        client.validate_operation_args(args)
        if operation == "diagnostics-log":
            diagnostics = client.finish_client_diagnostics(diagnostics)
            result = client.make_result(
                ok=True,
                operation=operation,
                result={"events": client.read_diagnostics_events(limit=args.limit)},
                client_diagnostics=diagnostics,
            )
            print(json.dumps(result, indent=2))
            return 0

        if not client.operation_uses_queue(operation):
            application, session = None, None
        else:
            with client.outlook_operation_queue(
                operation,
                queue_timeout_sec=args.queue_timeout_sec,
            ) as queue_meta:
                diagnostics["queue"] = queue_meta
                with client.outlook_com_lock():
                    diagnostics["com_lock_acquired"] = True
                    application, session = client.connect_outlook(diagnostics=diagnostics)
                    if operation == "diagnostics-probe":
                        diagnostics = client.finish_client_diagnostics(diagnostics)
                        result = client.make_result(
                            ok=True,
                            operation=operation,
                            result={"com_available": True},
                            queue=queue_meta,
                            client_diagnostics=diagnostics,
                        )
                        client.write_diagnostics_event(diagnostics, include_success=True)
                        print(json.dumps(result, indent=2))
                        return 0
                    result = client.dispatch_operation(args, application=application, session=session)
                    result["queue"] = queue_meta
                    result.setdefault("client_diagnostics", client.finish_client_diagnostics(diagnostics))
                    print(json.dumps(result, indent=2))
                    return 0 if result["ok"] else 1
        result = client.dispatch_operation(args, application=application, session=session)
        result["queue"] = queue_meta
        result.setdefault("client_diagnostics", client.finish_client_diagnostics(diagnostics))
    except client.QueueTimeoutError as exc:
        diagnostics["queue"] = exc.metadata or queue_meta
        diagnostics = client.finish_client_diagnostics(diagnostics, failure_kind="queue_timeout", exception=exc)
        client.write_diagnostics_event(diagnostics)
        result = client.make_result(
            ok=False,
            operation=getattr(args, "operation", "unknown"),
            stderr=f"queue_timeout: {exc}",
            exit_code=76,
            queue=exc.metadata or queue_meta,
            client_diagnostics=diagnostics,
        )
    except client.OutlookBusyError as exc:
        diagnostics["queue"] = queue_meta
        diagnostics = client.finish_client_diagnostics(diagnostics, failure_kind="outlook_busy_lock", exception=exc)
        client.write_diagnostics_event(diagnostics)
        result = client.make_result(
            ok=False,
            operation=getattr(args, "operation", "unknown"),
            stderr=f"outlook_busy: {exc}",
            exit_code=75,
            queue=queue_meta,
            client_diagnostics=diagnostics,
        )
    except client.OutlookComUnavailableError as exc:
        diagnostics = exc.diagnostics or diagnostics
        diagnostics.setdefault("failure_kind", exc.failure_kind)
        diagnostics["queue"] = queue_meta
        client.write_diagnostics_event(diagnostics)
        result = client.make_result(
            ok=False,
            operation=getattr(args, "operation", "unknown"),
            stderr=f"{exc.failure_kind}: {exc}",
            exit_code=74,
            queue=queue_meta,
            client_diagnostics=diagnostics,
        )
    except ValueError as exc:
        diagnostics = client.finish_client_diagnostics(diagnostics, exception=exc)
        result = client.make_result(
            ok=False,
            operation=getattr(args, "operation", "unknown"),
            stderr=str(exc),
            exit_code=2,
            queue=queue_meta,
            client_diagnostics=diagnostics,
        )
    except Exception as exc:
        diagnostics = client.finish_client_diagnostics(diagnostics, failure_kind="unexpected_client_error", exception=exc)
        client.write_diagnostics_event(diagnostics)
        result = client.make_result(
            ok=False,
            operation=getattr(args, "operation", "unknown"),
            stderr=str(exc),
            exit_code=1,
            queue=queue_meta,
            client_diagnostics=diagnostics,
        )

    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else int(result.get("exit_code") or 1)


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))
