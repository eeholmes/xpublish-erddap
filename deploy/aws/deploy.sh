#!/bin/bash
# Create or update the xpublish-erddap test server on AWS (issue #17).
#
#   deploy/aws/deploy.sh                 # uses the defaults below
#   GIT_REF=my-branch deploy/aws/deploy.sh   # run another branch/tag/commit
#
# Needs: AWS CLI v2 logged in to the target account, and an Arraylake API key
# (read-only is enough; any org's key can read the public CEFI repo) in
# TOKEN_FILE. The key goes to an SSM SecureString parameter, as in the other
# stacks in this account; it is never put in the template, the instance's
# disk, or the repo.
set -euo pipefail

PROFILE=${DEPLOY_PROFILE:-greenfield}
# Not AWS_REGION: JupyterHub sets that for its own account.
REGION=${DEPLOY_REGION:-us-east-2}   # the account's policy allows EC2 only here
STACK=${STACK:-xpublish-erddap-demo}
PARAM=${PARAM:-/xpublish-erddap-demo/arraylake-token}
TOKEN_FILE=${TOKEN_FILE:-$HOME/.arraylake-token}
GIT_REF=${GIT_REF:-main}
MAX_RESPONSE_MB=${MAX_RESPONSE_MB:-500}

aws_() { aws --profile "$PROFILE" --region "$REGION" "$@"; }

if ! aws_ ssm get-parameter --name "$PARAM" --query Parameter.Name \
    --output text >/dev/null 2>&1; then
  aws_ ssm put-parameter --name "$PARAM" --type SecureString \
    --description "Arraylake API key for the xpublish-erddap test server" \
    --value "file://$TOKEN_FILE" \
    --tags Key=project,Value=xpublish-erddap >/dev/null
  echo "stored the Arraylake key in $PARAM"
fi

aws_ cloudformation deploy \
  --stack-name "$STACK" \
  --template-file "$(dirname "$0")/stack.yaml" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    "TokenParameter=$PARAM" "GitRef=$GIT_REF" "MaxResponseMb=$MAX_RESPONSE_MB" \
  --tags project=xpublish-erddap teardown=2026-11-13

aws_ cloudformation describe-stacks --stack-name "$STACK" \
  --query 'Stacks[0].Outputs' --output table
echo "The instance takes a few minutes to install; then check it with:"
echo "  python deploy/check_clients.py <Url>"
