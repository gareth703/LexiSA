/** Hands a File selected on the home page to the /review route across client-side navigation. */

let pendingFile: File | null = null;

export function setPendingUploadFile(file: File): void {
  pendingFile = file;
}

/** Reads and clears the pending file so a page refresh or repeat visit doesn't reuse it. */
export function takePendingUploadFile(): File | null {
  const file = pendingFile;
  pendingFile = null;
  return file;
}
