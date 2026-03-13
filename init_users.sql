-- ── dbs_admin（管理账号）──
CREATE USER 'dbs_admin'@'%' IDENTIFIED WITH mysql_native_password BY 'Dbs@Admin2026';
GRANT SELECT, INSERT, UPDATE, DELETE,
      CREATE, DROP, INDEX, ALTER,
      CREATE VIEW, SHOW VIEW,
      CREATE ROUTINE, ALTER ROUTINE, EXECUTE,
      REFERENCES, TRIGGER, LOCK TABLES
ON *.* TO 'dbs_admin'@'%';

-- ── dbs_query（只读账号）──
CREATE USER 'dbs_query'@'%' IDENTIFIED WITH mysql_native_password BY 'Dbs@Query2026';
GRANT SELECT, SHOW VIEW ON *.* TO 'dbs_query'@'%';

FLUSH PRIVILEGES;
