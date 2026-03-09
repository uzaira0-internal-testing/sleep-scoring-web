/**
 * Chunked file reader for multi-GB files.
 * Uses File.slice() to read in manageable chunks without loading entire file.
 */

const DEFAULT_CHUNK_SIZE = 50 * 1024 * 1024; // 50MB per chunk

export interface ChunkReadProgress {
  bytesRead: number;
  totalBytes: number;
  percent: number;
}

/**
 * Read a file as text in chunks, calling onChunk for each piece.
 * For CSV files that need to be parsed as a whole, this concatenates
 * chunks into a single string with progress reporting.
 */
export async function readFileAsText(
  file: File,
  onProgress?: (progress: ChunkReadProgress) => void,
  chunkSize: number = DEFAULT_CHUNK_SIZE,
): Promise<string> {
  const totalBytes = file.size;
  const decoder = new TextDecoder("utf-8");
  const chunks: string[] = [];
  let bytesRead = 0;

  while (bytesRead < totalBytes) {
    const end = Math.min(bytesRead + chunkSize, totalBytes);
    const slice = file.slice(bytesRead, end);
    const buffer = await slice.arrayBuffer();
    chunks.push(decoder.decode(buffer, { stream: end < totalBytes }));
    bytesRead = end;

    onProgress?.({
      bytesRead,
      totalBytes,
      percent: (bytesRead / totalBytes) * 100,
    });
  }

  return chunks.join("");
}

/**
 * Read a file and return lines as an async iterator.
 * More memory-efficient for very large files.
 */
export async function* readFileLines(
  file: File,
  chunkSize: number = DEFAULT_CHUNK_SIZE,
): AsyncGenerator<string, void, undefined> {
  const totalBytes = file.size;
  const decoder = new TextDecoder("utf-8");
  let bytesRead = 0;
  let leftover = "";

  while (bytesRead < totalBytes) {
    const end = Math.min(bytesRead + chunkSize, totalBytes);
    const slice = file.slice(bytesRead, end);
    const buffer = await slice.arrayBuffer();
    const text = leftover + decoder.decode(buffer, { stream: end < totalBytes });

    const lines = text.split("\n");
    leftover = lines.pop() ?? "";

    for (const line of lines) {
      yield line;
    }

    bytesRead = end;
  }

  if (leftover) {
    yield leftover;
  }
}
