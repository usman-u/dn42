# Routing Policy

This network is designed to perform cold potato routing.

| LPREF | Criterion                                                 | Notes                   |
|-------|-----------------------------------------------------------|-------------------------|
| 500   | Prefix is anycast and originates from USMAN               | Reserved for future use |
| 300   | Prefix originates rom peer (ASPATH length = 1)            |                         |
| 210   | Prefix matches the neighbour's country                    |                         |
| 200   | Prefix matches the neigbour's region                      |                         |
| 100   | Default                                                   |                         |

The latency of eBGP peerings are measured (in us) and are set on ingress. The is used to inform the BGP path selection algorithm, and is the often the tie-breaker after LPREF and ASPATH length are equal.