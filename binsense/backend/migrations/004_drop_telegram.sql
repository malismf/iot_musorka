-- Telegram-бота в системе больше нет: события видны в веб-приложении
-- (лента, всплывающие сообщения по WebSocket, кнопка «Принято»).
-- Убираем привязку чатов, журнал отправленных уведомлений и настройки рассылки.

DROP TABLE IF EXISTS notifications;
DROP TABLE IF EXISTS telegram_links;
ALTER TABLE users DROP COLUMN IF EXISTS telegram_chat_id;
ALTER TABLE users DROP COLUMN IF EXISTS notify_info;
ALTER TABLE users DROP COLUMN IF EXISTS notify_enabled;
