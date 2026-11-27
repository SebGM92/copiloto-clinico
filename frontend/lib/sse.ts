export type SSEEvent = { event: string; data: unknown };

/**
 * Lee un stream text/event-stream de una respuesta fetch.
 * EventSource del navegador solo hace GET; para un POST con JSON hay que parsear a mano.
 */
export async function* readSSE(response: Response): AsyncGenerator<SSEEvent> {
  if (!response.body) throw new Error("La respuesta no tiene cuerpo");
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value.replace(/\r\n/g, "\n");

    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      let event = "message";
      const dataLines: string[] = [];
      for (const line of raw.split("\n")) {
        if (line.startsWith(":")) continue; // comentario o keep-alive
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
      }
      if (dataLines.length) yield { event, data: JSON.parse(dataLines.join("\n")) };
    }
  }
}
