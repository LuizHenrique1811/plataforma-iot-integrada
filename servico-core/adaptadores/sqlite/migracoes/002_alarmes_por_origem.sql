-- Mesma mudança da migração 004 da central: um alarme aberto por regra, dispositivo e origem.

UPDATE alarmes SET estado = 'resolvido', resolvido_em = strftime('%Y-%m-%dT%H:%M:%f+00:00','now')
WHERE estado <> 'resolvido' AND EXISTS (
    SELECT 1 FROM alarmes AS b
    WHERE b.inquilino_id = alarmes.inquilino_id AND b.regra_id = alarmes.regra_id
      AND b.dispositivo_id = alarmes.dispositivo_id AND b.origem = alarmes.origem AND b.estado <> 'resolvido'
      AND (b.ocorrido_em, b.id) > (alarmes.ocorrido_em, alarmes.id)
);

DROP INDEX IF EXISTS alarmes_um_aberto;
CREATE UNIQUE INDEX alarmes_um_aberto_por_origem ON alarmes (inquilino_id, regra_id, dispositivo_id, origem)
    WHERE estado <> 'resolvido';
