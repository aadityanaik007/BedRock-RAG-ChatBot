# Active Parking Session After Exit

## Symptoms

A customer reports that they have already exited the garage,
but the parking session still appears active.

## Possible Causes

- Exit event was not received by the backend.
- License plate recognition failed at the exit.
- Garage device lost connectivity.
- Session closure processing failed after the exit event.

## Investigation Steps

1. Retrieve the parking session.
2. Check whether an exit timestamp exists.
3. Check recent entry and exit events.
4. Check garage device connectivity.
5. Review backend processing errors for the session.

## Resolution

If the exit event exists but the session remains open,
investigate the session closure workflow.

If no exit event exists, verify garage device connectivity
and license plate recognition events.
