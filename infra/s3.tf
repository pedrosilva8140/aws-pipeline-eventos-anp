resource "aws_s3_bucket" "dados" {
  bucket        = local.nome_bucket
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "dados" {
  bucket = aws_s3_bucket.dados.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "dados" {
  bucket = aws_s3_bucket.dados.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # SSE-S3, sem chave KMS gerenciada pelo cliente
    }
  }
}

# Pacote da Lambda (gerado por scripts/empacotar.py). Fica em artefatos/, nunca em entrada/,
# para não disparar o evento da própria Lambda.
resource "aws_s3_object" "pacote_lambda" {
  bucket      = aws_s3_bucket.dados.id
  key         = local.chave_pacote
  source      = local.caminho_pacote
  source_hash = filebase64sha256(local.caminho_pacote)
}

resource "aws_s3_bucket_notification" "entrada" {
  bucket = aws_s3_bucket.dados.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.processador.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = local.prefixo_entrada
    filter_suffix       = ".csv"
  }

  depends_on = [aws_lambda_permission.s3_invoca_lambda]
}
