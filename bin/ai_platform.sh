#!/bin/bash

# A sample script to submit a job to Google AI Platform.

JOB_ID="example_$(date '+%Y%m%d%H%M%S')"

gcloud ai-platform jobs submit training "${JOB_ID}" \
  --region us-east1 \
  --master-image-uri gcr.io/cloud-builders/gcloud \
  --labels "user=test,hoge=fuga" \
  -- \
  --help
