import { AppShell } from "@/components/shell/app-shell";
import { StudioWorkspace } from "@/components/studio/studio-workspace";

export default function StudioConversationPage({
  params,
}: {
  params: { conversationId: string };
}) {
  return (
    <AppShell>
      <StudioWorkspace conversationId={params.conversationId} />
    </AppShell>
  );
}
