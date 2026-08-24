/**
 * Server yuborgan ikona NOMINI lucide-react komponentiga aylantiradi (S-05).
 *
 * NEGA XARITA, dinamik import EMAS: `lucide-react` dan nom bo'yicha
 * dinamik olish butun kutubxonani bundle'ga tortadi (~1 MB). Xarita esa
 * faqat haqiqatan ishlatiladigan ikonalarni qoldiradi — tree-shaking
 * ishlayveradi.
 *
 * Serverda yangi bo'lim qo'shilib, ikonasi bu yerda bo'lmasa — sahifa
 * BUZILMAYDI, `Circle` zaxira ikonasi ko'rinadi. Menyu bandi baribir
 * ishlaydi, faqat ikonasi umumiy bo'ladi.
 */
import {
  BarChart3,
  Banknote,
  Briefcase,
  CalendarCheck,
  CalendarClock,
  CalendarX,
  Circle,
  Clapperboard,
  ClipboardList,
  Clock,
  FileSpreadsheet,
  FileText,
  Filter,
  FolderArchive,
  FolderOpen,
  GraduationCap,
  LayoutDashboard,
  ListTodo,
  MapPin,
  Megaphone,
  MessageSquare,
  Building2,
  Network,
  NotebookPen,
  Package,
  PencilLine,
  Scale,
  ScrollText,
  Settings,
  ShieldAlert,
  Target,
  TimerReset,
  TrendingUp,
  UserCheck,
  UserPlus,
  Users,
  type LucideIcon,
} from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  BarChart3,
  Banknote,
  Briefcase,
  CalendarCheck,
  CalendarClock,
  CalendarX,
  Clapperboard,
  ClipboardList,
  Clock,
  FileSpreadsheet,
  FileText,
  Filter,
  FolderArchive,
  FolderOpen,
  GraduationCap,
  LayoutDashboard,
  ListTodo,
  MapPin,
  Megaphone,
  MessageSquare,
  Building2,
  Network,
  NotebookPen,
  Package,
  PencilLine,
  Scale,
  ScrollText,
  Settings,
  ShieldAlert,
  Target,
  TimerReset,
  TrendingUp,
  UserCheck,
  UserPlus,
  Users,
};

export function sectionIcon(name: string): LucideIcon {
  return ICONS[name] ?? Circle;
}
