# Local demo fleet smell scenarios

The four runnable local Docker services (`user_service`, `order_service`,
`payment_service`, and `notification_service`) intentionally model all ten
architectural smells in MDT's default local demo registry. No separate smell
service or fixture container exists.

`payment-service` is intentionally isolated. The other three services carry
the circular, bottleneck, coupling, chatty, fan-out, and hub patterns. Their
two shared-database connection declarations point to a database host string,
not a fifth service. The local demo history seeds the dependency-growth and
API-contract-change scenarios.

Use **Restore Local Demo Fleet** in Overview to restore this exact four-service
topology and then open **Architectural Smells** to inspect all ten detections.
