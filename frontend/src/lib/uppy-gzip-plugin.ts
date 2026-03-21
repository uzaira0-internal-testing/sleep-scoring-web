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
import type { Meta } from "@uppy/utils";

interface GzipCompressorOpts extends PluginOpts {
  /** Minimum file size (bytes) to compress. Smaller files are passed through. */
  minSize?: number;
  /** Maximum file size (bytes) to compress. Larger files skip compression — browser gzip is too slow. */
  maxSize?: number;
}

// Use Record<string, never> for Body to match Uppy's default type parameter
type DefaultBody = Record<string, never>;

export class GzipCompressorPlugin extends BasePlugin<GzipCompressorOpts, Meta, DefaultBody> {
  static VERSION = "1.0.0";
  override id = "GzipCompressor";
  override type = "preprocessor";

  private readonly minSize: number;
  private readonly maxSize: number;

  constructor(uppy: Uppy<Meta, DefaultBody>, opts?: GzipCompressorOpts) {
    super(uppy, opts ?? {});
    this.minSize = opts?.minSize ?? 1024; // 1KB minimum
    this.maxSize = opts?.maxSize ?? 500 * 1024 * 1024; // 500MB — browser gzip is too slow above this
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
      if (originalSize < this.minSize || originalSize > this.maxSize) {
        // Too small or too large — skip compression
        if (originalSize > this.maxSize) {
          console.debug(`[GzipCompressor] ${file.name}: ${(originalSize / 1024 / 1024).toFixed(0)}MB exceeds ${(this.maxSize / 1024 / 1024).toFixed(0)}MB limit, skipping compression`);
        }
        this.uppy.setFileMeta(fileID, {
          is_gzip: "false",
          filename: file.name,
        });
        continue;
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      this.uppy.emit("preprocess-progress" as any, file, {
        mode: "determinate",
        message: "Compressing...",
        value: 0,
      });

      try {
        const blob = file.data instanceof Blob ? file.data : new Blob([file.data as BlobPart]);
        const compressedBlob = await this.compressBlob(blob);

        const compressionRatio = ((1 - compressedBlob.size / originalSize) * 100).toFixed(1);
        console.debug(
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

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      this.uppy.emit("preprocess-progress" as any, file, {
        mode: "determinate",
        message: "Compressed",
        value: 1,
      });
    }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    this.uppy.emit("preprocess-complete" as any, fileIDs);
  };

  private async compressBlob(blob: Blob): Promise<Blob> {
    const stream = blob.stream().pipeThrough(new CompressionStream("gzip"));
    return new Response(stream).blob();
  }
}
