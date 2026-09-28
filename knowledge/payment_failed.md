# Payment Failed

## Overview

This issue occurs when a customer attempts to complete payment for a parking session, but the payment is not successfully completed.

A failed payment does not always mean the same thing happened at every layer. The payment provider, backend service, and parking application may each have different states that need to be checked.

## Common Symptoms

- Customer receives a "payment failed" message.
- Parking session remains unpaid.
- Customer retries payment multiple times.
- Payment status is shown as failed or incomplete.
- Customer reports that their card was declined.
- Application shows an error after payment submission.

## Possible Causes

- Card was declined by the payment provider.
- Payment request timed out.
- Payment gateway returned an error.
- Network failure occurred during payment processing.
- Payment method was invalid or expired.
- Required payment information was missing.
- Backend payment service failed before completing the transaction.
- Payment succeeded at the gateway, but the application failed to record the final status.

## Investigation Steps

1. Retrieve the parking session.
2. Retrieve the related payment transaction.
3. Check the internal payment status.
4. Check the payment gateway status.
5. Compare the gateway status with the internal transaction status.
6. Review the payment error code or failure message.
7. Check whether multiple payment attempts were made.
8. Review backend logs around the transaction timestamp.
9. Confirm whether the parking session was updated after the payment attempt.

## Important Status Scenarios

### Scenario 1: Gateway Status = Failed

If the payment gateway reports the transaction as failed, review the gateway error message or decline reason.

Possible examples:

- card declined
- insufficient funds
- expired card
- invalid payment information

The customer may need to retry using a valid payment method.

### Scenario 2: Gateway Status = Successful, Internal Status = Failed

This indicates that the external payment may have completed successfully, but the application failed to update its internal transaction state.

Possible causes include:

- database update failure
- processing timeout
- downstream service failure
- event processing failure

Do not immediately ask the customer to retry payment because this could result in a duplicate charge.

The transaction should first be reconciled with the gateway status.

### Scenario 3: Gateway Status = Pending

A pending gateway transaction should not immediately be treated as failed.

The payment status should be rechecked before another payment attempt is initiated.

### Scenario 4: No Gateway Transaction Found

If no transaction exists at the payment gateway, the payment request may have failed before reaching the gateway.

Check:

- application logs
- API request failures
- network errors
- payment-service availability

## Resolution Guidance

- If the gateway confirms failure, allow the customer to retry payment.
- If the gateway confirms success but the internal system does not, reconcile the internal payment state before retrying.
- If the payment is pending, wait for or retrieve the final gateway status.
- If no gateway request exists, investigate the payment service or API failure.
- If multiple successful transactions exist for the same parking session, follow the duplicate-payment procedure.

## Data Required for Investigation

- parking session ID
- transaction ID
- garage ID
- payment timestamp
- internal payment status
- gateway payment status
- payment error code
- payment method type
- number of payment attempts

## Support Response Guidance

Support should avoid stating that a payment definitely failed until both the internal transaction status and gateway status have been reviewed.

If the available information is insufficient, request the transaction or session details required for further investigation.
