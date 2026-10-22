"""Objetos do domínio no formato dos schemas do contrato (openapi.yaml)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from dominio.catalogo import Area, ChaveDeApi, Dominio, Inquilino, Site
from dominio.consultas import EstadoDoDispositivo, MedicaoConsultada, RejeitadaConsultada
from dominio.modelos import DispositivoCadastrado, Perfil
from dominio.paginacao import Pagina


def instante(valor: datetime | None) -> str | None:
    if valor is None:
        return None
    return valor.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _sem_nulos(dados: dict[str, Any]) -> dict[str, Any]:
    return {chave: valor for chave, valor in dados.items() if valor is not None}


def pagina_json(pagina: Pagina[Any], converter: Callable[[Any], dict[str, Any]]) -> dict[str, Any]:
    return {
        "itens": [converter(item) for item in pagina.itens],
        "pagina": pagina.pagina,
        "tamanho": pagina.tamanho,
        "total": pagina.total,
    }


def inquilino_json(inquilino: Inquilino) -> dict[str, Any]:
    return {"id": inquilino.id, "nome": inquilino.nome}


def chave_json(chave: ChaveDeApi, segredo: str | None = None) -> dict[str, Any]:
    dados = {"id": chave.id, "papel": chave.papel, "descricao": chave.descricao, "criado_em": instante(chave.criado_em)}
    if segredo is not None:
        dados["chave"] = segredo
    return _sem_nulos(dados)


def dominio_json(dominio: Dominio) -> dict[str, Any]:
    return _sem_nulos({"id": dominio.id, "nome": dominio.nome, "descricao": dominio.descricao})


def perfil_json(perfil: Perfil) -> dict[str, Any]:
    return {
        "id": perfil.id,
        "nome": perfil.nome,
        "intervalo_envio_s": perfil.intervalo_envio_s,
        "grandezas": [
            _sem_nulos({"grandeza": g.grandeza, "unidade": g.unidade, "minimo": g.minimo, "maximo": g.maximo})
            for g in perfil.grandezas.values()
        ],
    }


def site_json(site: Site) -> dict[str, Any]:
    return _sem_nulos({"id": site.id, "nome": site.nome, "geo": site.geo})


def area_json(area: Area) -> dict[str, Any]:
    return _sem_nulos({"id": area.id, "nome": area.nome, "geo": area.geo})


def dispositivo_json(dispositivo: DispositivoCadastrado, token: str | None = None) -> dict[str, Any]:
    dados = _sem_nulos(
        {
            "id": dispositivo.id,
            "perfil": dispositivo.perfil,
            "dominio": dispositivo.dominio,
            "site": dispositivo.site,
            "area": dispositivo.area,
            "fabricante": dispositivo.fabricante,
            "firmware": dispositivo.firmware,
            "inquilino": dispositivo.inquilino,
            "criado_em": instante(dispositivo.criado_em),
        }
    )
    dados["revogado_em"] = instante(dispositivo.revogado_em)
    if token is not None:
        dados["token"] = token
    return dados


def medicao_json(medicao: MedicaoConsultada) -> dict[str, Any]:
    return _sem_nulos(
        {
            "timestamp": instante(medicao.timestamp),
            "grandeza": medicao.grandeza,
            "valor": medicao.valor,
            "unidade": medicao.unidade,
            "suspeita": medicao.suspeita,
            "id_mensagem": medicao.id_mensagem,
            "via": medicao.via,
        }
    )


def estado_json(estado: EstadoDoDispositivo) -> dict[str, Any]:
    return {
        "dispositivo": estado.dispositivo,
        "situacao": estado.situacao.value,
        "ultimo_contato": instante(estado.ultimo_contato),
        "grandezas": [medicao_json(medicao) for medicao in estado.grandezas],
    }


def rejeitada_json(rejeitada: RejeitadaConsultada) -> dict[str, Any]:
    return {
        "id": rejeitada.id,
        "recebido_em": instante(rejeitada.recebido_em),
        "etapa": rejeitada.etapa,
        "motivo": rejeitada.motivo,
        "erros": list(rejeitada.erros),
        "origem": rejeitada.origem,
        "carga": rejeitada.carga,
    }
