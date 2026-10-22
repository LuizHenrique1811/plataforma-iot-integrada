"""Pipeline de ingestão no padrão Pipes and Filters (ADR-0008).

validar -> autorizar -> deduplicar -> enriquecer -> persistir

Cada filtro devolve None para seguir adiante ou um ResultadoIngestao para encerrar. Toda rejeição
vai para a fila de mensagens inválidas (DLQ) com a etapa e o motivo.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from dominio.modelos import (
    PAPEIS_QUE_INGEREM,
    DispositivoCadastrado,
    ErroDeCampo,
    Etapa,
    Medida,
    MensagemAceita,
    MensagemRejeitada,
    Motivo,
    Origem,
    Rejeicao,
    ResultadoIngestao,
    ResultadoLote,
    Situacao,
    TipoOrigem,
)
from dominio.unidades import UnidadeIncompativel, converter
from portas.contrato import ValidadorDeContrato
from portas.relogio import Relogio
from portas.repositorios import Catalogo, FilaDeRejeitadas, RepositorioDeIngestao

# Antes disso, o relógio do dispositivo certamente não estava acertado (ADR-0009).
TIMESTAMP_MINIMO = datetime(2000, 1, 1, tzinfo=UTC)

log = logging.getLogger("servico_core.ingestao")


class ObservadorDeIngestao(Protocol):
    """Interessado em cada mensagem aceita, como o motor de regras (padrão Observer, seção 7.2)."""

    def mensagem_aceita(self, mensagem: MensagemAceita) -> object: ...


@dataclass
class _Contexto:
    carga: Any
    origem: Origem
    recebido_em: datetime
    dispositivo: DispositivoCadastrado | None = None
    mensagem: MensagemAceita | None = None


class PipelineDeIngestao:
    def __init__(
        self,
        validador: ValidadorDeContrato,
        catalogo: Catalogo,
        repositorio: RepositorioDeIngestao,
        rejeitadas: FilaDeRejeitadas,
        relogio: Relogio,
        *,
        limite_dado_atual: timedelta = timedelta(minutes=5),
        tolerancia_futuro: timedelta = timedelta(minutes=5),
        observadores: tuple[ObservadorDeIngestao, ...] = (),
    ) -> None:
        self._validador = validador
        self._catalogo = catalogo
        self._repositorio = repositorio
        self._rejeitadas = rejeitadas
        self._relogio = relogio
        self._limite_dado_atual = limite_dado_atual
        self._tolerancia_futuro = tolerancia_futuro
        self._observadores = observadores
        self._filtros: tuple[Callable[[_Contexto], ResultadoIngestao | None], ...] = (
            self._validar,
            self._autorizar,
            self._deduplicar,
            self._enriquecer,
            self._persistir,
        )

    def processar(self, carga: Any, origem: Origem) -> ResultadoIngestao:
        contexto = _Contexto(carga=carga, origem=origem, recebido_em=self._relogio.agora())
        for filtro in self._filtros:
            resultado = filtro(contexto)
            if resultado is not None:
                return resultado
        raise AssertionError("o último filtro sempre devolve um resultado")

    def processar_lote(self, carga: Any, origem: Origem) -> ResultadoLote:
        """Processa cada mensagem do lote individualmente (RF-ING-03)."""
        erros = self._validador.validar_lote(carga)
        if erros:
            return ResultadoLote(erros_envelope=tuple(erros))
        return ResultadoLote(resultados=tuple(self.processar(item, origem) for item in carga["mensagens"]))

    def registrar_carga_ilegivel(self, conteudo: str, origem: Origem, detalhe: str) -> ResultadoIngestao:
        """Corpo que nem chega a ser JSON também vai para a DLQ."""
        contexto = _Contexto(carga=conteudo, origem=origem, recebido_em=self._relogio.agora())
        return self._rejeitar(contexto, Etapa.VALIDACAO, Motivo.JSON_INVALIDO, [ErroDeCampo("", detalhe)])

    # Filtros -------------------------------------------------------------------------------

    def _validar(self, ctx: _Contexto) -> ResultadoIngestao | None:
        if not isinstance(ctx.carga, dict):
            return self._rejeitar(
                ctx, Etapa.VALIDACAO, Motivo.FORA_DO_CONTRATO, [ErroDeCampo("", "a mensagem deve ser um objeto JSON")]
            )
        versao = ctx.carga.get("versao")
        if versao not in self._validador.versoes():
            suportadas = ", ".join(sorted(self._validador.versoes()))
            return self._rejeitar(
                ctx,
                Etapa.VALIDACAO,
                Motivo.VERSAO_NAO_SUPORTADA,
                [ErroDeCampo("/versao", f"versão {versao!r} não suportada; use: {suportadas}")],
            )
        erros = self._validador.validar(ctx.carga)
        if erros:
            return self._rejeitar(ctx, Etapa.VALIDACAO, Motivo.FORA_DO_CONTRATO, erros)
        return None

    def _autorizar(self, ctx: _Contexto) -> ResultadoIngestao | None:
        origem = ctx.origem
        if origem.inquilino is None:
            return self._rejeitar(
                ctx, Etapa.AUTORIZACAO, Motivo.ORIGEM_NAO_AUTORIZADA, [ErroDeCampo("", "credencial sem inquilino")]
            )
        if origem.tipo is TipoOrigem.CHAVE and origem.papel not in PAPEIS_QUE_INGEREM:
            return self._rejeitar(
                ctx,
                Etapa.AUTORIZACAO,
                Motivo.ORIGEM_NAO_AUTORIZADA,
                [ErroDeCampo("", f"o papel {origem.papel!r} não envia mensagens")],
            )
        if origem.dispositivo is not None and origem.dispositivo != ctx.carga["dispositivo"]:
            return self._rejeitar(
                ctx,
                Etapa.AUTORIZACAO,
                Motivo.DISPOSITIVO_DIVERGENTE,
                [ErroDeCampo("/dispositivo", f"a credencial é do dispositivo {origem.dispositivo!r}")],
            )
        if origem.canal is not None and origem.canal != ctx.carga["tipo"]:
            return self._rejeitar(
                ctx,
                Etapa.AUTORIZACAO,
                Motivo.TOPICO_DIVERGENTE,
                [ErroDeCampo("/tipo", f"mensagem do tipo {ctx.carga['tipo']!r} publicada no tópico {origem.canal!r}")],
            )
        return None

    def _deduplicar(self, ctx: _Contexto) -> ResultadoIngestao | None:
        id_mensagem = ctx.carga["id_mensagem"]
        if self._repositorio.ja_recebida(id_mensagem):
            return ResultadoIngestao(Situacao.DUPLICADA, id_mensagem=id_mensagem)
        return None

    def _enriquecer(self, ctx: _Contexto) -> ResultadoIngestao | None:
        carga = ctx.carga
        inquilino = ctx.origem.inquilino
        assert inquilino is not None  # garantido por _autorizar
        dispositivo = self._catalogo.obter_dispositivo(inquilino, carga["dispositivo"])
        if dispositivo is None:
            return self._rejeitar(
                ctx,
                Etapa.ENRIQUECIMENTO,
                Motivo.DISPOSITIVO_DESCONHECIDO,
                [ErroDeCampo("/dispositivo", "dispositivo não cadastrado no inquilino")],
            )
        ctx.dispositivo = dispositivo
        # No MQTT, o tópico precisa ser o do dispositivo (simplificação do RF-SEG-04, ADR-0018).
        origem = ctx.origem
        if origem.site is not None and (origem.site, origem.dominio) != (dispositivo.site, dispositivo.dominio):
            return self._rejeitar(
                ctx,
                Etapa.AUTORIZACAO,
                Motivo.TOPICO_DIVERGENTE,
                [
                    ErroDeCampo(
                        "",
                        f"o dispositivo publica em {dispositivo.site}/{dispositivo.dominio}, "
                        f"não em {origem.site}/{origem.dominio}",
                    )
                ],
            )

        timestamp, origem_timestamp = self._carimbar(
            carga.get("timestamp"), carga.get("origem_timestamp"), ctx.recebido_em
        )
        # Mitigação do ADR-0015: dados medidos depois da revogação não entram, mesmo vindos da borda.
        if dispositivo.revogado_em is not None and timestamp >= dispositivo.revogado_em:
            return self._rejeitar(
                ctx,
                Etapa.ENRIQUECIMENTO,
                Motivo.CREDENCIAL_REVOGADA,
                [ErroDeCampo("/timestamp", "medição posterior à revogação da credencial")],
            )

        tipo = carga["tipo"]
        if tipo == "comando":
            return self._rejeitar(
                ctx,
                Etapa.ENRIQUECIMENTO,
                Motivo.TIPO_NAO_ACEITO,
                [ErroDeCampo("/tipo", "comandos saem da plataforma; não são aceitos na ingestão")],
            )

        medidas: tuple[Medida, ...] = ()
        if tipo == "telemetria":
            normalizadas = self._normalizar_medidas(ctx, dispositivo, carga["medidas"])
            if isinstance(normalizadas, ResultadoIngestao):
                return normalizadas
            medidas = normalizadas

        local = carga.get("local") or {}
        ctx.mensagem = MensagemAceita(
            id_mensagem=carga["id_mensagem"],
            inquilino=inquilino,
            dispositivo=dispositivo.id,
            tipo=tipo,
            timestamp=timestamp,
            origem_timestamp=origem_timestamp,
            recebido_em=ctx.recebido_em,
            dominio=dispositivo.dominio,
            perfil=dispositivo.perfil,
            site=local.get("site") or dispositivo.site,
            area=local.get("area") or dispositivo.area,
            via=carga.get("via"),
            atual=ctx.recebido_em - timestamp <= self._limite_dado_atual,
            medidas=medidas,
            evento=carga.get("evento"),
            estado=carga.get("estado"),
            carga={**carga, "timestamp": _iso(timestamp), "origem_timestamp": origem_timestamp},
        )
        return None

    def _persistir(self, ctx: _Contexto) -> ResultadoIngestao:
        mensagem = ctx.mensagem
        assert mensagem is not None
        # A gravação do id_mensagem e dos dados é atômica; uma corrida entre reenvios resulta em duplicada.
        if not self._repositorio.persistir(mensagem):
            return ResultadoIngestao(Situacao.DUPLICADA, id_mensagem=mensagem.id_mensagem)
        for observador in self._observadores:
            try:
                observador.mensagem_aceita(mensagem)
            except Exception:
                # A mensagem já está gravada; uma falha no observador não pode desfazer a ingestão.
                log.exception("falha ao notificar %s", type(observador).__name__)
        return ResultadoIngestao(Situacao.ACEITA, id_mensagem=mensagem.id_mensagem, mensagem=mensagem)

    # Apoio ---------------------------------------------------------------------------------

    def _normalizar_medidas(
        self, ctx: _Contexto, dispositivo: DispositivoCadastrado, brutas: list[dict[str, Any]]
    ) -> tuple[Medida, ...] | ResultadoIngestao:
        perfil = self._catalogo.obter_perfil(dispositivo.inquilino, dispositivo.perfil)
        if perfil is None:
            return self._rejeitar(
                ctx,
                Etapa.ENRIQUECIMENTO,
                Motivo.PERFIL_DESCONHECIDO,
                [ErroDeCampo("/dispositivo", f"perfil {dispositivo.perfil!r} não encontrado")],
            )
        medidas = []
        for indice, bruta in enumerate(brutas):
            definicao = perfil.grandezas.get(bruta["grandeza"])
            if definicao is None:
                return self._rejeitar(
                    ctx,
                    Etapa.ENRIQUECIMENTO,
                    Motivo.GRANDEZA_FORA_DO_PERFIL,
                    [ErroDeCampo(f"/medidas/{indice}/grandeza", f"grandeza não definida no perfil {perfil.id!r}")],
                )
            valor = bruta["valor"]
            unidade = bruta.get("unidade") or definicao.unidade
            suspeita = False
            if isinstance(valor, (int, float)) and not isinstance(valor, bool):
                try:
                    valor = converter(float(valor), unidade, definicao.unidade)
                except UnidadeIncompativel as erro:
                    return self._rejeitar(
                        ctx,
                        Etapa.ENRIQUECIMENTO,
                        Motivo.UNIDADE_INCOMPATIVEL,
                        [ErroDeCampo(f"/medidas/{indice}/unidade", str(erro))],
                    )
                unidade = definicao.unidade
                # Fora da faixa do perfil a medida é marcada como suspeita, não recusada (RF-CEN-02).
                suspeita = definicao.fora_da_faixa(valor)
            medidas.append(Medida(bruta["grandeza"], valor, unidade, suspeita))
        return tuple(medidas)

    def _carimbar(self, bruto: str | None, origem_informada: str | None, recebido_em: datetime) -> tuple[datetime, str]:
        """Usa o timestamp da origem quando plausível; senão, a hora de recepção (ADR-0009)."""
        if bruto is None:
            return recebido_em, "recepcao"
        timestamp = datetime.fromisoformat(bruto).astimezone(UTC)
        if timestamp < TIMESTAMP_MINIMO or timestamp > recebido_em + self._tolerancia_futuro:
            return recebido_em, "recepcao"
        return timestamp, origem_informada or "dispositivo"

    def _rejeitar(self, ctx: _Contexto, etapa: Etapa, motivo: Motivo, erros: list[ErroDeCampo]) -> ResultadoIngestao:
        self._rejeitadas.registrar(
            MensagemRejeitada(
                recebido_em=ctx.recebido_em,
                inquilino=ctx.origem.inquilino,
                etapa=etapa,
                motivo=motivo,
                erros=tuple(erros),
                carga=ctx.carga,
                origem=ctx.origem.descricao(),
            )
        )
        id_mensagem = ctx.carga.get("id_mensagem") if isinstance(ctx.carga, dict) else None
        return ResultadoIngestao(
            Situacao.REJEITADA,
            id_mensagem=id_mensagem if isinstance(id_mensagem, str) else None,
            rejeicao=Rejeicao(etapa, motivo, tuple(erros)),
        )


def _iso(instante: datetime) -> str:
    return instante.astimezone(UTC).isoformat().replace("+00:00", "Z")
