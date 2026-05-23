"""
Multi-Language Support for IUT Appointment System
Supports English, Bangla, and Somali
"""

class Translations:
    """Translation dictionary for supported languages"""
    
    translations = {
        'en': {
            # Navigation
            'home': 'Home',
            'dashboard': 'Dashboard',
            'appointments': 'Appointments',
            'officers': 'Officers',
            'profile': 'Profile',
            'logout': 'Logout',
            'login': 'Login',
            'register': 'Register',
            
            # Common
            'submit': 'Submit',
            'cancel': 'Cancel',
            'save': 'Save',
            'delete': 'Delete',
            'edit': 'Edit',
            'back': 'Back',
            'next': 'Next',
            'previous': 'Previous',
            'search': 'Search',
            'filter': 'Filter',
            'export': 'Export',
            'import': 'Import',
            
            # Appointments
            'book_appointment': 'Book Appointment',
            'reschedule_appointment': 'Reschedule Appointment',
            'cancel_appointment': 'Cancel Appointment',
            'appointment_date': 'Appointment Date',
            'appointment_time': 'Appointment Time',
            'appointment_status': 'Status',
            'appointment_issue': 'Issue',
            'appointment_priority': 'Priority',
            'appointment_officer': 'Officer',
            'appointment_student': 'Student',
            'appointment_confirmed': 'Appointment Confirmed',
            'appointment_cancelled': 'Appointment Cancelled',
            'appointment_rescheduled': 'Appointment Rescheduled',
            
            # Status
            'pending': 'Pending',
            'approved': 'Approved',
            'in_progress': 'In Progress',
            'completed': 'Completed',
            'cancelled': 'Cancelled',
            'student_arrived': 'Student Arrived',
            
            # Priority
            'emergency': 'Emergency',
            'high': 'High',
            'normal': 'Normal',
            'low': 'Low',
            
            # Messages
            'success': 'Success',
            'error': 'Error',
            'warning': 'Warning',
            'info': 'Information',
            'loading': 'Loading...',
            'no_data': 'No data available',
            'confirm_delete': 'Are you sure you want to delete this?',
            'confirm_cancel': 'Are you sure you want to cancel this appointment?',
            
            # Feedback
            'leave_feedback': 'Leave Feedback',
            'rating': 'Rating',
            'comments': 'Comments',
            'submit_feedback': 'Submit Feedback',
            'feedback_submitted': 'Thank you for your feedback!',
            
            # Analytics
            'analytics': 'Analytics',
            'total_appointments': 'Total Appointments',
            'completed_appointments': 'Completed Appointments',
            'cancelled_appointments': 'Cancelled Appointments',
            'average_rating': 'Average Rating',
            'peak_hours': 'Peak Hours',
            'busiest_officers': 'Busiest Officers',
            
            # Settings
            'settings': 'Settings',
            'dark_mode': 'Dark Mode',
            'language': 'Language',
            'notifications': 'Notifications',
            'email_notifications': 'Email Notifications',
            'sms_notifications': 'SMS Notifications',
        },
        'bn': {
            # Navigation
            'home': 'হোম',
            'dashboard': 'ড্যাশবোর্ড',
            'appointments': 'অ্যাপয়েন্টমেন্ট',
            'officers': 'অফিসার',
            'profile': 'প্রোফাইল',
            'logout': 'লগআউট',
            'login': 'লগইন',
            'register': 'নিবন্ধন',
            
            # Common
            'submit': 'জমা দিন',
            'cancel': 'বাতিল করুন',
            'save': 'সংরক্ষণ করুন',
            'delete': 'মুছুন',
            'edit': 'সম্পাদনা করুন',
            'back': 'ফিরে যান',
            'next': 'পরবর্তী',
            'previous': 'পূর্ববর্তী',
            'search': 'খুঁজুন',
            'filter': 'ফিল্টার করুন',
            'export': 'রপ্তানি করুন',
            'import': 'আমদানি করুন',
            
            # Appointments
            'book_appointment': 'অ্যাপয়েন্টমেন্ট বুক করুন',
            'reschedule_appointment': 'অ্যাপয়েন্টমেন্ট পুনর্নির্ধারণ করুন',
            'cancel_appointment': 'অ্যাপয়েন্টমেন্ট বাতিল করুন',
            'appointment_date': 'অ্যাপয়েন্টমেন্টের তারিখ',
            'appointment_time': 'অ্যাপয়েন্টমেন্টের সময়',
            'appointment_status': 'অবস্থা',
            'appointment_issue': 'সমস্যা',
            'appointment_priority': 'অগ্রাধিকার',
            'appointment_officer': 'অফিসার',
            'appointment_student': 'শিক্ষার্থী',
            'appointment_confirmed': 'অ্যাপয়েন্টমেন্ট নিশ্চিত করা হয়েছে',
            'appointment_cancelled': 'অ্যাপয়েন্টমেন্ট বাতিল করা হয়েছে',
            'appointment_rescheduled': 'অ্যাপয়েন্টমেন্ট পুনর্নির্ধারণ করা হয়েছে',
            
            # Status
            'pending': 'অপেক্ষমাণ',
            'approved': 'অনুমোদিত',
            'in_progress': 'চলমান',
            'completed': 'সম্পন্ন',
            'cancelled': 'বাতিল',
            'student_arrived': 'শিক্ষার্থী উপস্থিত',
            
            # Priority
            'emergency': 'জরুরি',
            'high': 'উচ্চ',
            'normal': 'সাধারণ',
            'low': 'নিম্ন',
            
            # Messages
            'success': 'সফল',
            'error': 'ত্রুটি',
            'warning': 'সতর্কতা',
            'info': 'তথ্য',
            'loading': 'লোড হচ্ছে...',
            'no_data': 'কোন ডেটা উপলব্ধ নেই',
            'confirm_delete': 'আপনি কি এটি মুছতে চান?',
            'confirm_cancel': 'আপনি কি এই অ্যাপয়েন্টমেন্ট বাতিল করতে চান?',
            
            # Feedback
            'leave_feedback': 'প্রতিক্রিয়া দিন',
            'rating': 'রেটিং',
            'comments': 'মন্তব্য',
            'submit_feedback': 'প্রতিক্রিয়া জমা দিন',
            'feedback_submitted': 'আপনার প্রতিক্রিয়ার জন্য ধন্যবাদ!',
            
            # Analytics
            'analytics': 'বিশ্লেষণ',
            'total_appointments': 'মোট অ্যাপয়েন্টমেন্ট',
            'completed_appointments': 'সম্পন্ন অ্যাপয়েন্টমেন্ট',
            'cancelled_appointments': 'বাতিল অ্যাপয়েন্টমেন্ট',
            'average_rating': 'গড় রেটিং',
            'peak_hours': 'শীর্ষ ঘন্টা',
            'busiest_officers': 'সবচেয়ে ব্যস্ত অফিসার',
            
            # Settings
            'settings': 'সেটিংস',
            'dark_mode': 'ডার্ক মোড',
            'language': 'ভাষা',
            'notifications': 'বিজ্ঞপ্তি',
            'email_notifications': 'ইমেল বিজ্ঞপ্তি',
            'sms_notifications': 'এসএমএস বিজ্ঞপ্তি',
        },
        'so': {
            # Navigation
            'home': 'Guriga',
            'dashboard': 'Qaybta Hore',
            'appointments': 'Wakhtiyada Kulamka',
            'officers': 'Afhayeenka',
            'profile': 'Waxyaabaha',
            'logout': 'Ka Bax',
            'login': 'Gal',
            'register': 'Diiwaangeli',
            
            # Common
            'submit': 'Gudbiye',
            'cancel': 'Jooji',
            'save': 'Kaydi',
            'delete': 'Tirtir',
            'edit': 'Wax Ka Beddel',
            'back': 'Dib',
            'next': 'Xiga',
            'previous': 'Hore',
            'search': 'Raadi',
            'filter': 'Kala Sooc',
            'export': 'Soo Saari',
            'import': 'Soo Geji',
            
            # Appointments
            'book_appointment': 'Wakhtiga Kulamka Booki',
            'reschedule_appointment': 'Wakhtiga Kulamka Dib U Qor',
            'cancel_appointment': 'Wakhtiga Kulamka Jooji',
            'appointment_date': 'Maalintii Kulamka',
            'appointment_time': 'Wakhtiga Kulamka',
            'appointment_status': 'Xaalka',
            'appointment_issue': 'Arrintu',
            'appointment_priority': 'Muhiimadda',
            'appointment_officer': 'Afhayeenka',
            'appointment_student': 'Ardayga',
            'appointment_confirmed': 'Wakhtiga Kulamka Oo Xaqijiyay',
            'appointment_cancelled': 'Wakhtiga Kulamka Oo Joojiyay',
            'appointment_rescheduled': 'Wakhtiga Kulamka Oo Dib U Qoray',
            
            # Status
            'pending': 'Sugaya',
            'approved': 'Oggolnaan',
            'in_progress': 'Socdaalka',
            'completed': 'Dhammaystay',
            'cancelled': 'Joojiyay',
            'student_arrived': 'Ardaygu Yimid',
            
            # Priority
            'emergency': 'Degdeg',
            'high': 'Sarreeya',
            'normal': 'Caadi',
            'low': 'Hoose',
            
            # Messages
            'success': 'Guuldarane',
            'error': 'Khalad',
            'warning': 'Digniinta',
            'info': 'Macluumaad',
            'loading': 'Lagu Soo Celceliya...',
            'no_data': 'Macluumaad La Helin Maayo',
            'confirm_delete': 'Sidee ku tirtirtaa?',
            'confirm_cancel': 'Sidee ku joojisaa wakhtiga kulamka?',
            
            # Feedback
            'leave_feedback': 'Jeediso Feedback',
            'rating': 'Tirada',
            'comments': 'Faallooyin',
            'submit_feedback': 'Gudbiye Feedback',
            'feedback_submitted': 'Mahadsanid feedback-kaaga!',
            
            # Analytics
            'analytics': 'Falanqaynta',
            'total_appointments': 'Guud Ahaan Wakhtiyada Kulamka',
            'completed_appointments': 'Wakhtiyada Kulamka Dhammaystay',
            'cancelled_appointments': 'Wakhtiyada Kulamka Joojiyay',
            'average_rating': 'Tirada Caadiga Ah',
            'peak_hours': 'Saacadihii Ugu Badan',
            'busiest_officers': 'Afhayeenka Ugu Badan Shaqo',
            
            # Settings
            'settings': 'Hagitaannada',
            'dark_mode': 'Modka Madow',
            'language': 'Luqada',
            'notifications': 'Ogeysiisyo',
            'email_notifications': 'Ogeysiisyo Email',
            'sms_notifications': 'Ogeysiisyo SMS',
        }
    }

    @staticmethod
    def get(key, language='en', default=None):
        """
        Get a translation for a key in a specific language
        
        Args:
            key (str): Translation key
            language (str): Language code (en, bn, so)
            default (str): Default value if key not found
        
        Returns:
            str: Translated text or default
        """
        if language not in Translations.translations:
            language = 'en'
        
        return Translations.translations[language].get(key, default or key)

    @staticmethod
    def get_all(language='en'):
        """
        Get all translations for a language
        
        Args:
            language (str): Language code
        
        Returns:
            dict: All translations for the language
        """
        if language not in Translations.translations:
            language = 'en'
        
        return Translations.translations[language]

    @staticmethod
    def get_supported_languages():
        """
        Get list of supported languages
        
        Returns:
            list: List of language codes
        """
        return list(Translations.translations.keys())

    @staticmethod
    def add_translation(language, key, value):
        """
        Add or update a translation
        
        Args:
            language (str): Language code
            key (str): Translation key
            value (str): Translated value
        """
        if language not in Translations.translations:
            Translations.translations[language] = {}
        
        Translations.translations[language][key] = value

    @staticmethod
    def add_language(language_code, translations_dict):
        """
        Add a new language with its translations
        
        Args:
            language_code (str): Language code
            translations_dict (dict): Dictionary of translations
        """
        Translations.translations[language_code] = translations_dict
