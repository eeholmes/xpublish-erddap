#!/bin/bash
# Create or update the xpublish-erddap test server on AWS (issue #17).
#
#   deploy/aws/deploy.sh                 # uses the defaults below
#   GIT_REF=main deploy/aws/deploy.sh    # run another branch/tag/commit
#
# Needs: AWS CLI v2 logged in to the target account, and an Arraylake API key
# (read-only is enough; any org's key can read the public CEFI repo) in
# TOKEN_FILE. The key goes to Secrets Manager; it is never put in the template,
# the instance's disk, or the repo.
set -euo pipefail

PROFILE=${AWS_PROFILE:-greenfield}
REGION=${AWS_REGION:-us-east-2}   # the account's policy allows EC2 only here
STACK=${STACK:-xpublish-erddap-demo}
SECRET=${SECRET:-xpublish-erddap-demo/arraylake-token}
TOKEN_FILE=${TOKEN_FILE:-$HOME/.arraylake-token}
GIT_REF=${GIT_REF:-aws-test-server}
MAX_RESPONSE_MB=${MAX_RESPONSE_MB:-500}

aws_() { aws --profile "$PROFILE" --region "$REGION" "$@"; }

if ! arn=$(aws_ secretsmanager describe-secret --secret-id "$SECRET" \
    --query ARN --output text 2>/dev/null); then
  arn=$(aws_ secretsmanager create-secret --name "$SECRET" \
    --description "Arraylake API key for the xpublish-erddap test server" \
    --secret-string "file://$TOKEN_FILE" \
    --tags Key=project,Value=xpublish-erddap \
    --query ARN --output text)
  echo "created secret $SECRET"
fi

aws_ cloudformation deploy \
  --stack-name "$STACK" \
  --template-file "$(dirname "$0")/stack.yaml" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    "TokenSecretArn=$arn" "GitRef=$GIT_REF" "MaxResponseMb=$MAX_RESPONSE_MB" \
  --tags project=xpublish-erddap teardown=2026-11-13

aws_ cloudformation describe-stacks --stack-name "$STACK" \
  --query 'Stacks[0].Outputs' --output table
echo "The instance takes a few minutes to install; then check it with:"
echo "  python deploy/check_clients.py <Url>"
