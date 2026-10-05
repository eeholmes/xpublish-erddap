#!/bin/bash
# Remove the xpublish-erddap test server and everything it created (#17).
# Planned teardown date: 2026-11-13.
set -euo pipefail

PROFILE=${DEPLOY_PROFILE:-greenfield}
REGION=${DEPLOY_REGION:-us-east-2}
STACK=${STACK:-xpublish-erddap-demo}
PARAM=${PARAM:-/xpublish-erddap-demo/arraylake-token}

aws_() { aws --profile "$PROFILE" --region "$REGION" "$@"; }

# Instance, Elastic IP, security group, role: all in the stack.
aws_ cloudformation delete-stack --stack-name "$STACK"
aws_ cloudformation wait stack-delete-complete --stack-name "$STACK"
echo "stack $STACK deleted"

aws_ ssm delete-parameter --name "$PARAM"
echo "parameter $PARAM deleted"
echo "Also revoke the Arraylake API key in the ocean-icechunks org settings."
