#!/bin/bash
# Remove the xpublish-erddap test server and everything it created (#17).
# Planned teardown date: 2026-11-13.
set -euo pipefail

PROFILE=${AWS_PROFILE:-greenfield}
REGION=${AWS_REGION:-us-east-2}
STACK=${STACK:-xpublish-erddap-demo}
SECRET=${SECRET:-xpublish-erddap-demo/arraylake-token}

aws_() { aws --profile "$PROFILE" --region "$REGION" "$@"; }

# Instance, Elastic IP, security group, role: all in the stack.
aws_ cloudformation delete-stack --stack-name "$STACK"
aws_ cloudformation wait stack-delete-complete --stack-name "$STACK"
echo "stack $STACK deleted"

# Secrets Manager keeps a deleted secret for 7 days before it is gone.
aws_ secretsmanager delete-secret --secret-id "$SECRET" --recovery-window-in-days 7
echo "secret $SECRET scheduled for deletion"
echo "Also revoke the Arraylake API key in the ocean-icechunks org settings."
