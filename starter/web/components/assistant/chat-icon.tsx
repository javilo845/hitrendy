export type ChatIconName =
  | "conversations"
  | "compose"
  | "search"
  | "gallery"
  | "library"
  | "home"
  | "settings"
  | "plus"
  | "microphone"
  | "send"
  | "close"
  | "image"
  | "spinner";

const paths: Record<ChatIconName, JSX.Element> = {
  image: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="8.5" cy="9.5" r="1.5" />
      <path d="m4 17 4.5-4.5L12 16l3-3 5 5" />
    </>
  ),
  conversations: (
    <>
      <path d="M4 7h16" />
      <path d="M4 12h16" />
      <path d="M4 17h10" />
    </>
  ),
  compose: (
    <>
      <path d="M4 20h4.5L19 9.5a2.12 2.12 0 0 0-3-3L5.5 17 4 20Z" />
      <path d="M14.5 5.5 18.5 9.5" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6" />
      <path d="m20 20-4.3-4.3" />
    </>
  ),
  gallery: (
    <>
      <rect x="3.5" y="4.5" width="17" height="15" rx="3" />
      <circle cx="9" cy="10" r="1.6" />
      <path d="m4.5 17.5 4.6-4.6a1.8 1.8 0 0 1 2.5 0l4.4 4.4" />
      <path d="m14.5 15.5 1.6-1.6a1.8 1.8 0 0 1 2.5 0l1.9 1.9" />
    </>
  ),
  library: (
    <>
      <path d="M20 14a3 3 0 0 1-3 3H9l-4 3V7a3 3 0 0 1 3-3h9a3 3 0 0 1 3 3Z" />
    </>
  ),
  home: (
    <>
      <path d="M4 10.5 12 4l8 6.5" />
      <path d="M6 9.8V19a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V9.8" />
      <path d="M10 20v-5h4v5" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M12 3.2v2.1M12 18.7v2.1M20.8 12h-2.1M5.3 12H3.2M18.2 5.8l-1.5 1.5M7.3 16.7l-1.5 1.5M18.2 18.2l-1.5-1.5M7.3 7.3 5.8 5.8" />
    </>
  ),
  plus: (
    <>
      <path d="M12 5.5v13" />
      <path d="M5.5 12h13" />
    </>
  ),
  microphone: (
    <>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0" />
      <path d="M12 18v3" />
    </>
  ),
  send: (
    <>
      <path d="M5 12h13" />
      <path d="m12.5 6 6 6-6 6" />
    </>
  ),
  close: (
    <>
      <path d="m6 6 12 12" />
      <path d="m18 6-12 12" />
    </>
  ),
  spinner: (
    <>
      <path d="M12 4a8 8 0 0 1 8 8" />
      <path d="M12 20a8 8 0 0 1-8-8" opacity="0.35" />
    </>
  ),
};

export function ChatIcon({ name }: { name: ChatIconName }) {
  return (
    <svg
      className="chat-icon"
      data-icon={name}
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {paths[name]}
    </svg>
  );
}
