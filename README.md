<div align="center">

<img src="logo.svg" width="68" alt="Logo do bsystem's">

# bsystem's · estúdio gratuito de sites

**Crie, personalize e publique sua presença digital com autonomia.**

[![Modelos](https://img.shields.io/badge/modelos-376-a6e85e?style=for-the-badge)](#modelos)
[![Licença MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-17201b?style=for-the-badge)](LICENSE)
[![GitHub Pages](https://img.shields.io/badge/site-GitHub_Pages-17201b?style=for-the-badge)](https://brunnojob.github.io/source-coppy/)
[![Validar e publicar](https://github.com/brunnojob/source-coppy/actions/workflows/pages.yml/badge.svg)](https://github.com/brunnojob/source-coppy/actions/workflows/pages.yml)

[**Abrir o estúdio**](https://brunnojob.github.io/source-coppy/) · [**Gestão de negócios**](https://brunnojob.github.io/source-coppy/operations.html) · [**Contratar criação + landing page + divulgação — R$ 250**](https://mpago.la/1iN25Xz)

</div>

![Prévia do editor multipágina](docs/editor-preview.jpg)

## O projeto

Um construtor visual gratuito para brasileiros: escolha um dos **376 modelos**, edite textos e imagens, organize seções e páginas e exporte HTML ou um projeto multipágina em ZIP. O editor roda no GitHub Pages, sem cadastro e sem servidor obrigatório. Os dados locais do projeto ficam no navegador; exporte o JSON para backup editável.

O serviço opcional de **R$ 250** cobre criação de site, landing page e divulgação. O pagamento é feito pelo [link do Mercado Pago](https://mpago.la/1iN25Xz). A confirmação ocorre na conta do vendedor, que entra em contato com o comprador após a aprovação. O site estático não processa pagamentos nem libera recursos automaticamente.

## Ferramentas gratuitas

- Visualização real dos modelos em telas de computador, tablet e celular.
- Editor de páginas com duplicação, reordenação, blocos de texto, galeria e chamadas para ação.
- Ajuste de identidade: cores, tipografia, título, texto, imagem de capa, descrição para buscadores e e-mail de contato.
- Upload de PNG, JPEG e WebP de até 5 MB, com redimensionamento e incorporação no HTML exportado.
- Projetos salvos localmente; importação e exportação de JSON; HTML individual e ZIP multipágina.
- Ferramentas de contagem de palavras, contraste de cores e criação de endereços amigáveis.
- Painel de gestão opcional para clientes, tarefas, estoque e caixa, conectado a uma API própria hospedada por você.

A gestão com usuários e dados compartilhados exige o backend Python/Docker e hospedagem separada. O exemplo de PDV registra vendas no navegador; não cobra, emite nota fiscal ou valida pagamentos.

## Modelos

| Coleção | Quantidade | Exemplos |
| --- | ---: | --- |
| Sites | 104 | Barbearia, café, clínica, academia, arquitetura, fotografia |
| Landing pages | 104 | Curso, produto, evento, lançamento, imóvel, newsletter |
| Bases SaaS | 104 | CRM, análises, agenda, suporte, projetos, estoque |
| Caixa local | 64 | Café, moda, pet shop, floricultura, livraria |
| **Total** | **376** | **47 nichos com oito composições cada** |

Os modelos combinam composições editoriais, imagens, conteúdo, cores, silhuetas e seções por nicho e categoria. Cada projeto continua personalizável. As bases SaaS e de caixa são demonstrações locais; sistemas completos requerem implementação adicional.

## Executar localmente

```bash
npm ci --ignore-scripts
npm test
python -m venv .venv
source .venv/bin/activate
pip install -r server/requirements.txt -r server/requirements-test.txt
python -m unittest discover -s tests -p 'test_*.py' -v
python -m http.server 8000
```

Abra `http://localhost:8000/`. No Windows, ative o ambiente com `.venv\\Scripts\\activate`. Para executar a API, consulte [a documentação de hospedagem](docs/SELF_HOSTING.md).

## Publicação

O workflow [pages.yml](.github/workflows/pages.yml) executa os testes JavaScript e Python a cada push e pull request. No `main`, publica os arquivos estáticos no GitHub Pages somente após a validação. Em **Settings → Pages**, selecione **GitHub Actions** como origem de implantação.

## Contribuir

Issues e pull requests são bem-vindos. Inclua uma descrição do problema, passos de reprodução e imagens quando alterar um layout. Mantenha os modelos utilizáveis em telas pequenas e sem dependência obrigatória de serviços pagos.

## Licença

[MIT](LICENSE). O editor e os modelos são gratuitos; o preço de R$ 250 refere-se somente ao serviço profissional opcional.
