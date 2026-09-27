-- Деления на роли больше нет: любой пользователь системы — администратор.

ALTER TABLE users DROP COLUMN IF EXISTS role;
