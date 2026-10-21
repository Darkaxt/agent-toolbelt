# Network evidence

## Supplied packet captures

Use explicit offline input (`tshark -r <capture>`) when analyzing a supplied file. Omitting offline input can select a live interface. Keep capture filters and display filters distinct: `-Y` filters displayed decoded packets. Resolve installed field names and decoding before building an extraction.

Check capture time span, packet loss/truncation indicators and vantage point before interpreting absence. Summarize protocols and conversations, then pivot on the relevant flow, DNS names or available TLS handshake metadata. Encrypted application content is not automatically visible. SYN-without-ACK is a connection attempt; a single such packet does not prove a failed connection, especially in a one-sided capture. Follow the stream and available responses/retransmissions.

Primary source: [TShark manual](https://www.wireshark.org/docs/man-pages/tshark.html). File extraction, credential recovery and live capture are separate operations from the initial offline question.

## Zeek timing and suspected beaconing

Preserve originator/responder roles, `uid`, protocol, service/port and timestamp. For timing analysis, group by originator, responder, responder port and protocol before sorting. Combining different services into a single host-pair sequence can manufacture or obscure a pattern. A global displayed-frame interval is not a per-service measurement.

Compute successive intervals only within the selected group. With enough observations, coefficient of variation is standard deviation divided by mean; explicitly state the sample/population convention and handle zero mean and insufficient data. Low variation is a candidate periodicity signal. Health checks and scheduled clients can be equally regular; corroborate with endpoint identity, service purpose, DNS/TLS context and the capture window. Irregular timing alone does not exclude C2.

Primary source: [Zeek conn.log fields](https://docs.zeek.org/en/current/reference/logs/conn.html). Timing calculations identify a hypothesis, not a measured malware-detection accuracy or automatic containment decision.
