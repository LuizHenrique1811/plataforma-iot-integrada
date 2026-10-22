-- Um alarme aberto por regra, dispositivo e origem. Cada nó abre e resolve os alarmes que gera; os que
-- chegam da borda são abertos e resolvidos pelos eventos "alarme" e "alarme_resolvido" (RF-PRO-05).

-- Antes do índice novo, fecha alarmes repetidos que ficaram abertos (fica o mais recente de cada grupo).
UPDATE alarmes AS a SET estado = 'resolvido', resolvido_em = now()
WHERE a.estado <> 'resolvido' AND EXISTS (
    SELECT 1 FROM alarmes AS b
    WHERE b.inquilino_id = a.inquilino_id AND b.regra_id = a.regra_id AND b.dispositivo_id = a.dispositivo_id
      AND b.origem = a.origem AND b.estado <> 'resolvido'
      AND (b.ocorrido_em, b.id::text) > (a.ocorrido_em, a.id::text)
);

DROP INDEX IF EXISTS alarmes_um_aberto;
CREATE UNIQUE INDEX alarmes_um_aberto_por_origem ON alarmes (inquilino_id, regra_id, dispositivo_id, origem)
    WHERE estado <> 'resolvido';
