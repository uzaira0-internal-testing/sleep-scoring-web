/**
 * Custom Uppy preprocessor plugin that compresses files using the browser's
 * native CompressionStream API (gzip). Uses streaming to avoid loading
 * the entire file into memory.
 *
 * After compression, updates the Uppy file with:
 * - The compressed blob as the new file data
 * - TUS metadata: filename (original), is_gzip: "true"
 */
import type Uppy from "@uppy/core";
import { BasePlugin, type PluginOpts } from "@uppy/core";

interface GzipCompressorOpts extends PluginOpts {
  /** Minimum file size (bytes) to compress. Smaller files are passed through. */
  minSize?: number;
}

export class GzipCompressorPlugin extends BasePlugin<GzipCompressorOpts> {
  static override readonly VERSION = "1.0.0";
  override readonly id = "GzipCompressor";
  override readonly type = "preprocessor";

  private readonly minSize: number;

  constructor(uppy: Uppy, opts?: GzipCompressorOpts) {
    super(uppy, opts ?? {});
    this.minSize = opts?.minSize ?? 1024; // 1KB minimum
  }

  override install(): void {
    this.uppy.addPreProcessor(this.compress);
  }

  override uninstall(): void {
    this.uppy.removePreProcessor(this.compress);
  }

  private compress = async (fileIDs: string[]): Promise<void> => {
    for (const fileID of fileIDs) {
      const file = this.uppy.getFile(fileID);
      if (!file?.data) continue;

      const originalSize = file.size ?? 0;
      if (originalSize < this.minSize) {
        // Small file — skip compression, mark as not gzipped
        this.uppy.setFileMeta(fileID, {
          is_gzip: "false",
          filename: file.name,
        });
        continue;
      }

      this.uppy.emit("preprocess-progress" as any, file, {
        mode: "determinate",
        message: "Compressing...",
        value: 0,
      });

      try {
        const blob = file.data instanceof Blob ? file.data : new Blob([file.data]);
        const compressedBlob = await this.compressBlob(blob);

        const compressionRatio = ((1 - compressedBlob.size / originalSize) * 100).toFixed(1);
        console.log(
          `[GzipCompressor] ${file.name}: ${(originalSize / 1024 / 1024).toFixed(1)}MB → ${(compressedBlob.size / 1024 / 1024).toFixed(1)}MB (${compressionRatio}% smaller)`
        );

        this.uppy.setFileState(fileID, {
          data: compressedBlob,
          size: compressedBlob.size,
        });
        this.uppy.setFileMeta(fileID, {
          is_gzip: "true",
          filename: file.name,
          original_size: String(originalSize),
          compressed_size: String(compressedBlob.size),
        });
      } catch (err) {
        console.warn(`[GzipCompressor] Failed to compress ${file.name}, uploading uncompressed:`, err);
        this.uppy.setFileMeta(fileID, {
          is_gzip: "false",
          filename: file.name,
        });
      }

      this.uppy.emit("preprocess-progress" as any, file, {
        mode: "determinate",
        message: "Compressed",
        value: 1,
      });
    }

    this.uppy.emit("preprocess-complete" as any, fileIDs);
  };

  private async compressBlob(blob: Blob): Promise<Blob> {
    const stream = blob.stream().pipeThrough(new CompressionStream("gzip"));
    return new Response(stream).blob();
  }
}
