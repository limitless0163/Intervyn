/** Enter confirms an IME candidate before it should submit a form.
 * Safari can report isComposing=false for that key, but still supplies 229.
 */
export function isImeConfirm(event: {
  key: string;
  isComposing: boolean;
  keyCode: number;
}): boolean {
  return event.key === "Enter" && (event.isComposing || event.keyCode === 229);
}
