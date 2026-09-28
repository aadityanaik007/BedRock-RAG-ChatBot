# Incorrect Parking Rate

## Symptoms

A customer believes the amount charged does not match the expected parking rate.

## Possible Causes

- Incorrect garage rate configuration.
- Event pricing was active.
- Validation was not applied.
- Parking duration exceeded the validation window.

## Investigation Steps

1. Retrieve the parking session.
2. Check entry and exit timestamps.
3. Retrieve the garage rate configuration.
4. Check active event rates.
5. Check validation status.
6. Recalculate the expected parking charge.
