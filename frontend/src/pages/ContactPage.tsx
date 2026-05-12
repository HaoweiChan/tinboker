import React from 'react';
import { Mail, Clock, MessageCircle, AtSign } from 'lucide-react';
import { Card, CardContent } from '@/components/ui';
import { AppLogo } from '@/components/logo/AppLogo';

interface ContactItemProps {
  icon: React.ReactNode;
  title: string;
  content: React.ReactNode;
  iconBgColor: string;
  iconColor: string;
}

const ContactItem: React.FC<ContactItemProps> = ({ 
  icon, 
  title, 
  content, 
  iconBgColor, 
  iconColor 
}) => {
  return (
    <div className="flex items-start gap-4 p-2">
      <div className={`w-12 h-12 rounded-full ${iconBgColor} flex items-center justify-center flex-shrink-0 mt-1`}>
        <div className={iconColor}>
          {icon}
        </div>
      </div>
      <div>
        <h3 className="font-bold text-lg text-slate-900 dark:text-slate-50 mb-1">{title}</h3>
        <div className="text-slate-600 dark:text-slate-400 text-base font-medium">
          {content}
        </div>
      </div>
    </div>
  );
};

export const ContactPage: React.FC = () => {
  return (
    <div className="min-h-screen flex flex-col bg-slate-50 dark:bg-slate-950 transition-colors duration-300">

      <main className="flex-1 py-12 md:py-20">
        <div className="container mx-auto max-w-3xl px-4">
          <h1 className="flex items-center justify-center gap-2 text-4xl font-bold text-slate-900 dark:text-slate-50 mb-8">
            <span>聯絡</span>
            <AppLogo size={40} className="inline-flex translate-y-1" />
          </h1>
          
          <Card className="border-none shadow-sm bg-white dark:bg-slate-900">
            <CardContent className="p-8 md:p-12">
              <p className="text-slate-600 dark:text-slate-400 text-lg mb-6 leading-relaxed">
                我們重視每一位使用者的聲音。若您有任何產品建議、合作想法或使用疑問，歡迎隨時與我們聯繫。
              </p>
              
              <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400 mb-12 bg-slate-50 dark:bg-slate-800/50 p-4 rounded-lg w-fit">
                <Clock size={18} className="text-accent-info" />
                <span className="text-sm font-medium">客服回覆時間：週一至週五 11:00-17:00（國定及例假日除外）</span>
              </div>

              <div className="space-y-8">
                {/* Email */}
                <ContactItem 
                  icon={<Mail size={24} />}
                  title="電子郵件"
                  content={
                    <a href="mailto:contact@trendbrief.com" className="text-accent-info dark:text-accent-info hover:underline">
                      contact@trendbrief.com
                    </a>
                  }
                  iconBgColor="bg-accent-info-soft dark:bg-accent-info/30"
                  iconColor="text-accent-info dark:text-accent-info"
                />

                {/* Line */}
                <ContactItem 
                  icon={<MessageCircle size={24} />}
                  title="官方 Line 帳號"
                  content={
                    <a href="#" className="text-accent-info dark:text-accent-info hover:underline">
                      @trendbrief
                    </a>
                  }
                  iconBgColor="bg-green-100 dark:bg-green-900/30"
                  iconColor="text-green-600 dark:text-green-500"
                />

                {/* Threads */}
                <ContactItem 
                  icon={<AtSign size={24} />}
                  title="官方 Threads 帳號"
                  content={
                    <a href="https://www.threads.net/@trendbrief" target="_blank" rel="noopener noreferrer" className="text-accent-info dark:text-accent-info hover:underline">
                      @trendbrief
                    </a>
                  }
                  iconBgColor="bg-slate-100 dark:bg-slate-800"
                  iconColor="text-slate-700 dark:text-slate-300"
                />
              </div>
            </CardContent>
          </Card>
        </div>
      </main>

    </div>
  );
};

export default ContactPage;
