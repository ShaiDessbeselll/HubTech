-- Execute este script no MySQL Workbench (ou use: python scripts/instalar.py)
-- Banco já existente? Use: python scripts/migrar_crm.py (não apaga dados)
CREATE DATABASE IF NOT EXISTS hubtech CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE hubtech;

CREATE TABLE IF NOT EXISTS usuarios (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nome VARCHAR(100) NOT NULL,
  email VARCHAR(150) UNIQUE NOT NULL,
  senha_hash VARCHAR(255) NOT NULL,
  perfil ENUM('admin','operador') NOT NULL DEFAULT 'operador',
  ativo TINYINT(1) NOT NULL DEFAULT 1,
  criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS importacoes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  usuario_id INT NOT NULL,
  nome_arquivo VARCHAR(255),
  origem VARCHAR(50),
  qtd_lidos INT DEFAULT 0,
  qtd_registros INT DEFAULT 0,
  qtd_duplicados INT DEFAULT 0,
  qtd_rejeitados INT DEFAULT 0,
  status VARCHAR(30),
  data_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);

CREATE TABLE IF NOT EXISTS demandas (
  id INT AUTO_INCREMENT PRIMARY KEY,
  importacao_id INT NOT NULL,
  produto VARCHAR(100),
  origem VARCHAR(100),
  destino VARCHAR(100),
  peso_ton DECIMAL(10,2),
  prazo DATE,
  frete DECIMAL(12,2),
  frete_estimado DECIMAL(12,2) NULL,
  hash_registro CHAR(64) UNIQUE NOT NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'NOVA',
  prioridade VARCHAR(10) NOT NULL DEFAULT 'MEDIA',
  responsavel_id INT NULL,
  criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
  atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (importacao_id) REFERENCES importacoes(id),
  FOREIGN KEY (responsavel_id) REFERENCES usuarios(id)
);

CREATE TABLE IF NOT EXISTS demanda_historico (
  id INT AUTO_INCREMENT PRIMARY KEY,
  demanda_id INT NOT NULL,
  usuario_id INT NULL,
  tipo VARCHAR(20) NOT NULL,
  de_valor VARCHAR(100),
  para_valor VARCHAR(100),
  texto TEXT,
  data_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (demanda_id) REFERENCES demandas(id)
);

CREATE TABLE IF NOT EXISTS registros_rejeitados (
  id INT AUTO_INCREMENT PRIMARY KEY,
  importacao_id INT NOT NULL,
  linha INT,
  motivo VARCHAR(255),
  conteudo TEXT,
  FOREIGN KEY (importacao_id) REFERENCES importacoes(id)
);

CREATE TABLE IF NOT EXISTS log_auditoria (
  id INT AUTO_INCREMENT PRIMARY KEY,
  usuario_id INT NULL,
  acao VARCHAR(100) NOT NULL,
  detalhe TEXT,
  data_hora DATETIME DEFAULT CURRENT_TIMESTAMP
);
