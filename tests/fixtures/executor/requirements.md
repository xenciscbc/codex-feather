Implement retry_delay(attempt, base, cap) in retry.py only.
attempt must be a nonnegative integer (bool is invalid); otherwise raise ValueError.
base and cap are finite nonnegative int/float values (bool is invalid); otherwise raise ValueError.
Return min(cap, base * 2**attempt), including attempt=0 and zero inputs.
Huge attempts such as 1000000000 must complete promptly without constructing an enormous integer or overflowing.
Choose an implementation that meets these requirements. Keep this file unchanged.
