/** 邮箱脱敏: abc***z@gmail.com */
export const maskEmail = (email: string): string => {
  const at = email.indexOf('@');
  if (at <= 3) return email; // 太短不处理
  const local = email.slice(0, at);
  const domain = email.slice(at);
  return `${local.slice(0, 3)}***${domain}`;
};
