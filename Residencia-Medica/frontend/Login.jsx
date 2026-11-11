import { useState } from "react";

/**
 * Tela de login.
 *
 * Requisito de usabilidade do projeto: interface pensada para usuários
 * idosos. Por isso: corpo de texto a partir de 18px, campos de 60px de
 * altura, alvo de toque grande, contraste alto, foco de teclado visível,
 * e o botão de mostrar senha (quem digita devagar erra mais).
 *
 * Integração: POST {API}/auth/login  ->  { access_token, expira_em, usuario }
 */

const API = "http://localhost:8000/api/v1";

const ROTA_INICIAL = {
  residente: "/portfolio",
  preceptor: "/avaliacoes",
  avaliador_intermediario: "/avaliacoes",
  administrador: "/gestao",
};

export default function Login({ aoEntrar = () => {} }) {
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [mostrarSenha, setMostrarSenha] = useState(false);
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [sessao, setSessao] = useState(null);

  async function entrar() {
    if (!email.trim() || !senha) {
      setErro("Preencha o email e a senha para entrar.");
      return;
    }
    setErro("");
    setEnviando(true);

    try {
      const resposta = await fetch(`${API}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), senha }),
      });

      if (resposta.status === 401) {
        setErro("Email ou senha incorretos. Confira e tente de novo.");
        return;
      }
      if (!resposta.ok) {
        setErro("O sistema não respondeu. Tente novamente em alguns instantes.");
        return;
      }

      const dados = await resposta.json();

      // O crachá fica em memória (React state / context).
      // NÃO use localStorage: qualquer script injetado na página lê de lá.
      // Em produção: token curto em memória + refresh token em cookie
      // httpOnly + SameSite=Strict, emitido pelo backend.
      setSessao(dados);
      setSenha("");
      aoEntrar(dados, ROTA_INICIAL[dados.usuario.papel] ?? "/");
    } catch {
      setErro("Sem conexão com o servidor. Verifique sua internet.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="tela">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,500;6..72,600&family=Source+Sans+3:wght@400;600;700&display=swap');

        .tela {
          --papel:      #EAEEEC;
          --carta:      #FFFFFF;
          --tinta:      #13262D;
          --tinta-fraca:#53686E;
          --cirurgico:  #0F6157;
          --cirurgico-f:#0A4740;
          --borda:      #C3CFCB;
          --alerta:     #8C2B22;

          --display: 'Newsreader', Georgia, serif;
          --corpo: 'Source Sans 3', system-ui, -apple-system, sans-serif;

          min-height: 100%;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 32px 20px 48px;
          background-color: var(--papel);
          background-image:
            linear-gradient(var(--borda) 1px, transparent 1px);
          background-size: 100% 34px;
          font-family: var(--corpo);
          color: var(--tinta);
        }
        .tela *, .tela *::before, .tela *::after { box-sizing: border-box; }

        /* Cartão desenhado como um crachá hospitalar: presilha, furo, faixa. */
        .cracha { width: 100%; max-width: 460px; }

        .presilha {
          width: 96px; height: 16px; margin: 0 auto;
          border: 2px solid var(--tinta-fraca);
          border-bottom: none;
          border-radius: 10px 10px 0 0;
          opacity: .55;
        }

        .carta {
          background: var(--carta);
          border: 1px solid var(--borda);
          border-radius: 14px;
          box-shadow: 0 18px 40px -28px rgba(19,38,45,.55);
          overflow: hidden;
        }

        .faixa {
          background: var(--cirurgico);
          padding: 22px 30px 20px;
          color: #EAF3F1;
          position: relative;
        }
        .furo {
          width: 54px; height: 9px; margin: 0 auto 16px;
          background: var(--papel);
          border-radius: 99px;
          box-shadow: inset 0 1px 2px rgba(0,0,0,.35);
        }
        .instituicao {
          font-size: 13px; font-weight: 700;
          letter-spacing: .13em; text-transform: uppercase;
          color: #9FC8C0; margin: 0 0 4px;
        }
        .titulo {
          font-family: var(--display);
          font-size: 30px; font-weight: 600; line-height: 1.15;
          margin: 0; color: #FFFFFF;
        }

        .miolo { padding: 30px; }

        .campo { margin-bottom: 22px; }
        .rotulo {
          display: block; font-size: 17px; font-weight: 600;
          margin-bottom: 8px; color: var(--tinta);
        }
        .entrada {
          width: 100%; height: 60px;
          padding: 0 16px;
          font-family: var(--corpo); font-size: 19px;
          color: var(--tinta); background: #FBFCFB;
          border: 2px solid var(--borda); border-radius: 8px;
          transition: border-color .12s ease, background-color .12s ease;
        }
        .entrada:hover:not(:disabled) { border-color: var(--tinta-fraca); }
        .entrada:focus-visible {
          outline: 3px solid var(--cirurgico);
          outline-offset: 2px;
          border-color: var(--cirurgico);
          background: #FFFFFF;
        }
        .entrada:disabled { background: #F0F2F1; color: var(--tinta-fraca); }

        .linha-senha { display: flex; gap: 10px; align-items: stretch; }
        .linha-senha .entrada { flex: 1; min-width: 0; }
        .olho {
          flex: 0 0 auto; padding: 0 16px; height: 60px;
          font-family: var(--corpo); font-size: 16px; font-weight: 600;
          color: var(--cirurgico); background: #FFFFFF;
          border: 2px solid var(--borda); border-radius: 8px;
          cursor: pointer;
        }
        .olho:hover { background: #F1F6F5; border-color: var(--cirurgico); }
        .olho:focus-visible { outline: 3px solid var(--cirurgico); outline-offset: 2px; }

        .erro {
          display: flex; gap: 10px; align-items: flex-start;
          font-size: 17px; line-height: 1.45;
          color: var(--alerta); background: #FBEFEE;
          border-left: 4px solid var(--alerta);
          padding: 14px 16px; border-radius: 0 8px 8px 0;
          margin-bottom: 22px;
        }

        .entrar {
          width: 100%; height: 62px;
          font-family: var(--corpo); font-size: 20px; font-weight: 700;
          color: #FFFFFF; background: var(--cirurgico);
          border: none; border-radius: 8px; cursor: pointer;
          transition: background-color .12s ease, transform .08s ease;
        }
        .entrar:hover:not(:disabled) { background: var(--cirurgico-f); }
        .entrar:active:not(:disabled) { transform: translateY(1px); }
        .entrar:focus-visible { outline: 3px solid var(--tinta); outline-offset: 3px; }
        .entrar:disabled { background: var(--tinta-fraca); cursor: progress; }

        .rodape {
          margin: 24px 0 0; text-align: center;
          font-size: 16px; line-height: 1.55; color: var(--tinta-fraca);
        }

        .aprovado { padding: 30px; }
        .selo {
          font-size: 12px; font-weight: 700; letter-spacing: .13em;
          text-transform: uppercase; color: var(--cirurgico);
          margin: 0 0 10px;
        }
        .nome {
          font-family: var(--display); font-size: 26px; font-weight: 600;
          margin: 0 0 4px;
        }
        .papel { font-size: 18px; color: var(--tinta-fraca); margin: 0 0 22px; }
        .validade {
          font-size: 15px; color: var(--tinta-fraca);
          border-top: 1px solid var(--borda); padding-top: 16px; margin: 0;
        }

        @media (max-width: 420px) {
          .titulo { font-size: 25px; }
          .faixa, .miolo, .aprovado { padding-left: 22px; padding-right: 22px; }
        }
        @media (prefers-reduced-motion: reduce) {
          .tela * { transition: none !important; }
        }
      `}</style>

      <div className="cracha">
        <div className="presilha" aria-hidden="true" />
        <div className="carta">
          <div className="faixa">
            <div className="furo" aria-hidden="true" />
            <p className="instituicao">Programa de Residência Médica</p>
            <h1 className="titulo">Entrar no sistema</h1>
          </div>

          {sessao ? (
            <div className="aprovado" role="status">
              <p className="selo">Acesso liberado</p>
              <p className="nome">{sessao.usuario.nome}</p>
              <p className="papel">{rotularPapel(sessao.usuario.papel)}</p>
              <p className="validade">
                Sessão válida por {Math.round(sessao.expira_em / 3600)} horas.
              </p>
            </div>
          ) : (
            <div className="miolo">
              {erro && (
                <p className="erro" role="alert">
                  <span aria-hidden="true">▲</span> {erro}
                </p>
              )}

              <div className="campo">
                <label className="rotulo" htmlFor="email">
                  Email institucional
                </label>
                <input
                  id="email"
                  className="entrada"
                  type="email"
                  autoComplete="username"
                  inputMode="email"
                  value={email}
                  disabled={enviando}
                  onChange={(e) => setEmail(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && entrar()}
                />
              </div>

              <div className="campo">
                <label className="rotulo" htmlFor="senha">
                  Senha
                </label>
                <div className="linha-senha">
                  <input
                    id="senha"
                    className="entrada"
                    type={mostrarSenha ? "text" : "password"}
                    autoComplete="current-password"
                    value={senha}
                    disabled={enviando}
                    onChange={(e) => setSenha(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && entrar()}
                  />
                  <button
                    type="button"
                    className="olho"
                    onClick={() => setMostrarSenha((v) => !v)}
                    aria-pressed={mostrarSenha}
                  >
                    {mostrarSenha ? "Ocultar" : "Mostrar"}
                  </button>
                </div>
              </div>

              <button
                type="button"
                className="entrar"
                onClick={entrar}
                disabled={enviando}
              >
                {enviando ? "Entrando…" : "Entrar"}
              </button>

              <p className="rodape">
                Esqueceu a senha? Procure a secretaria do programa.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function rotularPapel(papel) {
  return (
    {
      residente: "Residente",
      preceptor: "Preceptor",
      avaliador_intermediario: "Avaliador R4/R5",
      administrador: "Administrador",
    }[papel] ?? papel
  );
}
