---
name: terraform-modules
description: AWS and GCP Terraform module structure for interview platforms — EKS/GKE clusters, RDS PostgreSQL, ElastiCache Redis, S3 buckets, IAM roles, and VPC networking patterns.
---

# Terraform Modules Reference

---

## Module Structure

```
infrastructure/
├── environments/
│   ├── staging/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── terraform.tfvars
│   └── production/
│       ├── main.tf
│       ├── variables.tf
│       └── terraform.tfvars
└── modules/
    ├── eks-cluster/
    ├── rds-postgres/
    ├── elasticache-redis/
    ├── s3-audio-storage/
    └── iam-roles/
```

---

## EKS Cluster Module

```hcl
# modules/eks-cluster/main.tf
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = "1.29"
  vpc_id          = var.vpc_id
  subnet_ids      = var.private_subnet_ids

  cluster_endpoint_public_access  = false   # Private cluster
  cluster_endpoint_private_access = true

  # API server pods
  eks_managed_node_groups = {
    api_workers = {
      name           = "api-workers"
      instance_types = ["t3.medium"]
      min_size       = 2
      max_size       = 10
      desired_size   = 3
      labels         = { workload = "api" }
    }

    # LLM workers need more memory
    llm_workers = {
      name           = "llm-workers"
      instance_types = ["m6i.xlarge"]   # 4 vCPU, 16GB RAM
      min_size       = 1
      max_size       = 20
      desired_size   = 2
      labels         = { workload = "worker" }
      taints = [{
        key    = "workload"
        value  = "worker"
        effect = "NO_SCHEDULE"
      }]
    }
  }
}
```

---

## RDS PostgreSQL Module

```hcl
# modules/rds-postgres/main.tf
resource "aws_db_instance" "postgres" {
  identifier        = "${var.env}-interview-db"
  engine            = "postgres"
  engine_version    = "16.2"
  instance_class    = var.instance_class   # db.t3.medium (staging), db.m6g.large (prod)
  allocated_storage = 100
  storage_encrypted = true
  kms_key_id        = var.kms_key_arn

  db_name  = "interview_${var.env}"
  username = "interview_admin"
  password = random_password.db_password.result

  multi_az               = var.env == "production"
  deletion_protection    = var.env == "production"
  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"

  performance_insights_enabled = true
  monitoring_interval          = 60
  enabled_cloudwatch_logs_exports = ["postgresql"]

  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.main.name

  tags = { Environment = var.env }
}

# Store credentials in Secrets Manager
resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = aws_db_instance.postgres.username
    password = random_password.db_password.result
    host     = aws_db_instance.postgres.endpoint
    dbname   = aws_db_instance.postgres.db_name
  })
}
```

---

## S3 Audio Storage Module

```hcl
# modules/s3-audio-storage/main.tf
resource "aws_s3_bucket" "audio" {
  bucket = "${var.env}-interview-audio-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audio" {
  bucket = aws_s3_bucket.audio.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "audio" {
  bucket = aws_s3_bucket.audio.id
  rule {
    id     = "audio-retention"
    status = "Enabled"
    expiration { days = 90 }              # Delete audio after 90 days (GDPR)
    noncurrent_version_expiration { noncurrent_days = 7 }
  }
}

resource "aws_s3_bucket_public_access_block" "audio" {
  bucket                  = aws_s3_bucket.audio.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
```

---

## IAM Roles — Least Privilege

```hcl
# Pod identity for API service — only what it needs
resource "aws_iam_role" "api_service" {
  name = "${var.env}-interview-api"
  assume_role_policy = data.aws_iam_policy_document.eks_assume_role.json
}

resource "aws_iam_role_policy" "api_service" {
  role = aws_iam_role.api_service.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = ["arn:aws:secretsmanager:*:*:secret:interview/${var.env}/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject"]
        Resource = ["${aws_s3_bucket.audio.arn}/sessions/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:GenerateDataKey"]
        Resource = [var.kms_key_arn]
      }
    ]
  })
}
```
