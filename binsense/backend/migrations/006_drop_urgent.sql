-- Событие «Срочно вывезти» убрано: без подтверждений в интерфейсе оно лишь
-- дублировало «Контейнер заполнен».

DELETE FROM events WHERE type = 'full_urgent';

UPDATE devices
   SET state = state - 'urgent_sent' - 'full_since' - 'last_collection'
 WHERE state ?| ARRAY['urgent_sent', 'full_since', 'last_collection'];
