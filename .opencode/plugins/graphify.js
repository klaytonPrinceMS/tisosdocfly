// graphify plugin do OpenCode — formato V2 (setup + ctx.tool.hook).
//
// Antes era V1 (export nomeado GraphifyPlugin + evento "tool.execute.before" no
// objeto retornado por server()). O OpenCode V2 recusa esse formato com
// "Plugin must export a default definition with an id and an effect or setup
// function", e o aviso aparecia em TODO boot. A portabilidade de comportamento
// é direta: o V1 "tool.execute.before" virou ctx.tool.hook("execute.before"),
// e a mutação do input passou de output.args.command para event.input.command.
//
// IMPORTANTE: mantenha a string do lembrete SEM crase e SEM $(...). O hook
// prependa `echo "<lembrete>" ; <cmd>` no comando do usuário; crase dentro do
// echo duplo dispara substituição de comando do bash, o que corrompe a saída da
// ferramenta e executa silenciosamente o próprio comando graphify que só
// estamos sugerindo. Palavras simples renderizam bem no TUI do opencode.
//
// Separador ';' e não '&&': o PowerShell 5.1 do Windows rejeita '&&' como
// separador de instrução e quebrava o primeiro comando bash da sessão (#1646).
import { existsSync } from "fs";
import { join } from "path";

const LEMBRETE =
  '[graphify] knowledge graph at graphify-out/. For focused questions, run graphify query with your question (scoped subgraph, usually much smaller than GRAPH_REPORT.md) instead of grepping raw files. Read GRAPH_REPORT.md only for broad architecture context.';

export default {
  id: "graphify",
  async setup(ctx) {
    // Uma lembrança por sessão, não por comando — é o comportamento antigo.
    let lembrado = false;
    // ctx.location.directory é o diretório do projeto onde o plugin carregou;
    // substitui o { directory } que o V1 injetava no server().
    const dir = ctx.location?.directory ?? "";

    await ctx.tool.hook("execute.before", (event) => {
      if (lembrado) return;
      if (event.tool !== "bash") return;
      if (!existsSync(join(dir, "graphify-out", "graph.json"))) return;

      const comando = event.input?.command;
      if (typeof comando !== "string") return;

      event.input.command = `echo "${LEMBRETE}" ; ${comando}`;
      lembrado = true;
    });
  },
};
