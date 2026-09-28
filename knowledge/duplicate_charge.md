# Duplicate Parking Charge

## Symptoms

A customer reports being charged more than once for the same parking session.

## Possible Causes

- Multiple payment attempts.
- Gateway retry after a timeout.
- Duplicate transaction processing.
- Idempotency handling failure.

## Investigation Steps

1. Retrieve transactions for the parking session.
2. Compare transaction IDs and timestamps.
3. Check gateway statuses.
4. Confirm whether multiple transactions were settled.
5. Review duplicate-payment protection logs.
