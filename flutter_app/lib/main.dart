import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

const _apiBaseUrlFromEnv = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: '',
);

String _defaultApiBaseUrl() {
  if (_apiBaseUrlFromEnv.isNotEmpty) {
    return _apiBaseUrlFromEnv;
  }
  if (kIsWeb) {
    return Uri.base.origin;
  }
  return 'https://benconnect.cyou';
}

void _validateApiBaseUrl(String value) {
  final uri = Uri.tryParse(value);
  final isLocal = uri?.host == 'localhost' ||
      uri?.host == '127.0.0.1' ||
      uri?.host == '10.0.2.2';
  if (uri == null || uri.host.isEmpty || (uri.scheme != 'https' && !isLocal)) {
    throw StateError(
      'API_BASE_URL muss HTTPS verwenden. HTTP ist nur für lokale Entwicklung erlaubt.',
    );
  }
}

final apiBaseUrl = _defaultApiBaseUrl();

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  _validateApiBaseUrl(apiBaseUrl);
  await appLanguage.load();
  runApp(const LernApp());
}

class LernApp extends StatelessWidget {
  const LernApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<String>(
      valueListenable: appLanguage,
      builder: (context, languageCode, _) => LanguageScope(
        code: languageCode,
        child: MaterialApp(
          title: 'benconnect',
          debugShowCheckedModeBanner: false,
          theme: ThemeData(
            colorScheme: ColorScheme.fromSeed(
              seedColor: const Color(0xffff3b30),
              brightness: Brightness.light,
              surface: const Color(0xfff7f8fb),
            ),
            scaffoldBackgroundColor: const Color(0xfff3f4f8),
            appBarTheme: const AppBarTheme(
              backgroundColor: Colors.white,
              foregroundColor: Color(0xff111827),
              elevation: 0,
              centerTitle: false,
            ),
            cardTheme: CardTheme(
              color: Colors.white,
              elevation: 2,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
                side: const BorderSide(color: Color(0xffe5e7eb)),
              ),
            ),
            inputDecorationTheme: InputDecorationTheme(
              filled: true,
              fillColor: Colors.white,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: Color(0xffd1d5db)),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: Color(0xffd1d5db)),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: Color(0xff00c4cc), width: 2),
              ),
            ),
            elevatedButtonTheme: ElevatedButtonThemeData(
              style: ElevatedButton.styleFrom(
                minimumSize: const Size.fromHeight(48),
                backgroundColor: const Color(0xffff3b30),
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
              ),
            ),
            textButtonTheme: TextButtonThemeData(
              style: TextButton.styleFrom(
                foregroundColor: const Color(0xff00a7b0),
              ),
            ),
            chipTheme: ChipThemeData.fromDefaults(
              secondaryColor: const Color(0xff00c4cc),
              brightness: Brightness.light,
              labelStyle: const TextStyle(color: Color(0xff111827)),
            ),
            useMaterial3: true,
          ),
          home: const AppShell(),
        ),
      ),
    );
  }
}

class ApiClient {
  ApiClient({required this.baseUrl, this.token});

  final String baseUrl;
  String? token;

  Uri uri(String path, [Map<String, String>? query]) {
    return Uri.parse('$baseUrl$path').replace(queryParameters: query);
  }

  Map<String, String> get headers {
    return {
      'Accept': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };
  }

  Future<Map<String, dynamic>> getJson(
    String path, [
    Map<String, String>? query,
  ]) async {
    final response = await http.get(uri(path, query), headers: headers);
    return _decode(response);
  }

  Future<Map<String, dynamic>> postJson(
    String path,
    Map<String, dynamic> body,
  ) async {
    final response = await http.post(
      uri(path),
      headers: {...headers, 'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    return _decode(response);
  }

  Future<Map<String, dynamic>> putJson(
    String path,
    Map<String, dynamic> body,
  ) async {
    final response = await http.put(
      uri(path),
      headers: {...headers, 'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    return _decode(response);
  }

  Future<Map<String, dynamic>> deleteJson(String path) async {
    final response = await http.delete(uri(path), headers: headers);
    return _decode(response);
  }

  Future<Map<String, dynamic>> _decode(http.Response response) async {
    Map<String, dynamic> decoded;
    try {
      decoded = response.body.isEmpty
          ? <String, dynamic>{}
          : jsonDecode(response.body) as Map<String, dynamic>;
    } on FormatException {
      final preview = response.body.replaceAll(RegExp(r'\s+'), ' ').trim();
      final shortPreview =
          preview.length > 80 ? '${preview.substring(0, 80)}...' : preview;
      throw ApiException(
        'invalid_json',
        'Der Server hat kein JSON geliefert. Backend neu starten und '
            'API_BASE_URL pruefen. Status ${response.statusCode}: $shortPreview',
      );
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ApiException(
        decoded['error']?.toString() ?? 'request_failed',
        decoded['message']?.toString(),
      );
    }
    return decoded;
  }
}

class ApiException implements Exception {
  const ApiException(this.code, [this.message]);

  final String code;
  final String? message;

  @override
  String toString() => message ?? code;
}

class UserProfile {
  const UserProfile({
    required this.userId,
    required this.username,
    required this.role,
    required this.school,
    required this.className,
    required this.levelGerman,
    required this.levelMath,
    required this.levelEnglish,
    required this.levelBiology,
    required this.levelPgw,
    required this.levelSpanish,
    required this.levelArt,
    required this.proVerifiedGerman,
    required this.proVerifiedMath,
    required this.proVerifiedEnglish,
    required this.proVerifiedBiology,
    required this.proVerifiedPgw,
    required this.proVerifiedSpanish,
    required this.proVerifiedArt,
    required this.contactEmail,
    required this.notifyLadenEmail,
    required this.avatarUrl,
    required this.iservEmail,
    required this.schoolLogoUrl,
  });

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      userId: json['user_id'] as int,
      username: json['username']?.toString() ?? '',
      role: json['role']?.toString() ?? 'user',
      school: json['school']?.toString() ?? '',
      className: json['class_name']?.toString() ?? '',
      levelGerman: json['level_german']?.toString() ?? 'noob',
      levelMath: json['level_math']?.toString() ?? 'noob',
      levelEnglish: json['level_english']?.toString() ?? 'noob',
      levelBiology: json['level_biology']?.toString() ?? 'noob',
      levelPgw: json['level_pgw']?.toString() ?? 'noob',
      levelSpanish: json['level_spanish']?.toString() ?? 'noob',
      levelArt: json['level_art']?.toString() ?? 'noob',
      proVerifiedGerman: json['pro_verified_german'] == true,
      proVerifiedMath: json['pro_verified_math'] == true,
      proVerifiedEnglish: json['pro_verified_english'] == true,
      proVerifiedBiology: json['pro_verified_biology'] == true,
      proVerifiedPgw: json['pro_verified_pgw'] == true,
      proVerifiedSpanish: json['pro_verified_spanish'] == true,
      proVerifiedArt: json['pro_verified_art'] == true,
      contactEmail: json['contact_email']?.toString() ?? '',
      notifyLadenEmail: json['notify_laden_email'] == true,
      avatarUrl: json['avatar_url']?.toString() ?? '',
      iservEmail: json['iserv_email']?.toString() ?? '',
      schoolLogoUrl: json['school_logo_url']?.toString() ?? '',
    );
  }

  final int userId;
  final String username;
  final String role;
  final String school;
  final String className;
  final String levelGerman;
  final String levelMath;
  final String levelEnglish;
  final String levelBiology;
  final String levelPgw;
  final String levelSpanish;
  final String levelArt;
  final bool proVerifiedGerman;
  final bool proVerifiedMath;
  final bool proVerifiedEnglish;
  final bool proVerifiedBiology;
  final bool proVerifiedPgw;
  final bool proVerifiedSpanish;
  final bool proVerifiedArt;
  final String contactEmail;
  final bool notifyLadenEmail;
  final String avatarUrl;
  final String iservEmail;
  final String schoolLogoUrl;

  String levelFor(String subject) {
    return switch (subject) {
      'german' => levelGerman,
      'math' => levelMath,
      'english' => levelEnglish,
      'biology' => levelBiology,
      'pgw' => levelPgw,
      'spanish' => levelSpanish,
      'art' => levelArt,
      _ => 'noob',
    };
  }

  IconData? get roleIcon {
    return iconForRole(role);
  }

  bool get isStaff => role == 'admin' || role == 'dev' || role == 'teacher';
}

IconData? iconForRole(String? role) {
  return switch (role) {
    'admin' => Icons.admin_panel_settings,
    'dev' => Icons.developer_mode,
    'teacher' => Icons.school,
    _ => null,
  };
}

const appLanguages = [
  AppLanguage('el', 'Griechisch', 'Ελληνικά'),
  AppLanguage('sq', 'Albanisch', 'Shqip'),
  AppLanguage('hu', 'Ungarisch', 'Magyar'),
  AppLanguage('fi', 'Finnisch', 'Suomi'),
  AppLanguage('et', 'Estnisch', 'Eesti'),
  AppLanguage('tr', 'Türkisch', 'Türkçe'),
  AppLanguage('eu', 'Baskisch', 'Euskara'),
  AppLanguage('mt', 'Maltesisch', 'Malti'),
  AppLanguage('ga', 'Irisch', 'Gaeilge'),
  AppLanguage('cy', 'Walisisch', 'Cymraeg'),
  AppLanguage('pl', 'Polnisch', 'Polski'),
  AppLanguage('cs', 'Tschechisch', 'Čeština'),
  AppLanguage('sk', 'Slowakisch', 'Slovenčina'),
  AppLanguage('uk', 'Ukrainisch', 'Українська'),
  AppLanguage('ru', 'Russisch', 'Русский'),
  AppLanguage('hr', 'Kroatisch', 'Hrvatski'),
  AppLanguage('sr', 'Serbisch', 'Српски'),
  AppLanguage('bg', 'Bulgarisch', 'Български'),
  AppLanguage('sl', 'Slowenisch', 'Slovenščina'),
  AppLanguage('fr', 'Französisch', 'Français'),
  AppLanguage('es', 'Spanisch', 'Español'),
  AppLanguage('pt', 'Portugiesisch', 'Português'),
  AppLanguage('it', 'Italienisch', 'Italiano'),
  AppLanguage('ro', 'Rumänisch', 'Română'),
  AppLanguage('de', 'Deutsch', 'Deutsch'),
  AppLanguage('en', 'Englisch', 'English'),
  AppLanguage('nl', 'Niederländisch', 'Nederlands'),
  AppLanguage('sv', 'Schwedisch', 'Svenska'),
  AppLanguage('no', 'Norwegisch', 'Norsk'),
  AppLanguage('da', 'Dänisch', 'Dansk'),
  AppLanguage('is', 'Isländisch', 'Íslenska'),
];

const _baseText = {
  'language': 'Sprache',
  'logout': 'Logout',
  'home': 'Home',
  'chat': 'Chat',
  'shop': 'Laden',
  'profile': 'Profil',
  'admin': 'Admin',
  'learn': 'Lernen',
  'tips': 'Tipps',
  'motivation': 'Motivation',
  'learn_places': 'Lernorte',
  'login': 'Login',
  'invite_register': 'Mit Code registrieren',
  'setup_admin': 'Admin festlegen',
  'create_account': 'Konto erstellen',
  'username': 'Benutzername',
  'password': 'Passwort',
  'confirm_password': 'Passwort bestätigen',
  'invite_code': 'Einladungscode',
  'setup_only': 'Nur möglich, wenn kein Admin-Konto existiert.',
  'password_short': 'Passwort zu kurz.',
  'api': 'API',
  'hello': 'Hallo',
  'class': 'Klasse',
  'subject_chat': 'Fächer-Chat',
  'create_chat': 'Chat erstellen',
  'no_chat_open': 'Aktuell ist kein Fachchat offen.',
  'continue': 'Fortsetzen',
  'room_closed': 'Raum geschlossen',
  'join': 'Beitreten',
  'back': 'Zurück',
  'report': 'Melden',
  'write_message': 'Nachricht schreiben',
  'send': 'Senden',
  'points': 'Punkte',
  'save': 'Speichern',
  'refresh': 'Aktualisieren',
  'users': 'Nutzer',
  'codes': 'Codes',
  'chats': 'Chats',
  'ratings': 'Bewertungen',
  'teachers': 'Lehrer',
  'logo': 'Logo',
  'schools': 'Schulen',
  'licenses': 'Lizenzen',
  'administration': 'Administration',
  'german': 'Deutsch',
  'math': 'Mathe',
  'english': 'Englisch',
  'biology': 'Biologie',
  'pgw': 'PGW',
  'spanish': 'Spanisch',
  'art': 'Kunst',
  'store_text': 'Punkte einsehen und aktive Angebote kaufen.',
  'chat_text': 'Noob und Mittel können schreiben, sobald ein Pro im Fachraum ist.',
  'admin_text': 'Nutzer, Einladungscodes, Chats, Bewertungen und Laden verwalten.',
  'email': 'E-Mail-Adresse',
  'avatar': 'Avatar',
  'avatar_url': 'Avatar-Bild-URL',
  'iserv_connect': 'Mit IServ verbinden',
  'iserv_email': 'IServ-E-Mail',
  'notify_shop': 'Bei Laden-Käufen per E-Mail informieren',
  'change_password': 'Passwort ändern',
  'current_password': 'Aktuelles Passwort',
  'new_password': 'Neues Passwort',
  'confirm_new_password': 'Neues Passwort bestätigen',
  'saved': 'Gespeichert',
  'cancel': 'Abbrechen',
  'ok': 'OK',
  'create': 'Erstellen',
  'delete': 'Löschen',
  'edit': 'Bearbeiten',
  'copy': 'Kopieren',
  'active': 'Aktiv',
  'inactive': 'inaktiv',
  'set_password': 'Passwort setzen',
  'password_saved': 'Passwort gespeichert',
  'edit_role_school': 'Rolle und Schule bearbeiten',
  'set_class': 'Klasse setzen',
  'class_saved': 'Klasse gespeichert',
  'verify_pros': 'Pros verifizieren',
  'pro_verification_saved': 'Pro-Verifizierung gespeichert',
  'unban': 'Entsperren',
  'ban': 'Sperren',
  'ban_user': 'Nutzer sperren',
  'unban_user_q': 'Nutzer entsperren?',
  'ban_reason': 'Grund',
  'ban_reason_required': 'Bitte einen Sperrgrund eingeben.',
  'user_saved': 'Nutzer gespeichert',
  'user_banned': 'Nutzer gesperrt',
  'user_unbanned': 'Nutzer entsperrt',
  'no_users': 'Keine Nutzer gefunden.',
  'create_code': 'Code erstellen',
  'copy_code': 'Code kopieren',
  'delete_code': 'Code löschen',
  'code_copied': 'Code kopiert',
  'code_created': 'Code erstellt',
  'code_deleted': 'Code gelöscht',
  'delete_invite_code_q': 'Einladungscode löschen?',
  'delete_invite_code_msg': 'wird gelöscht und kann danach nicht mehr benutzt werden.',
  'no_open_codes': 'Keine offenen Codes.',
  'admin_code_licenses': 'Schul-Lizenzlimit',
  'teacher_code_licenses': 'Schule',
  'unlimited_zero': '0 = unbegrenzt',
  'positive_numbers': 'Bitte positive Zahlen oder 0 eingeben.',
  'code_licenses_saved': 'Code-Lizenzen gespeichert',
  'license_pool': 'Lizenz-Pool',
  'occupied': 'belegt',
  'role_licenses_unlimited': 'Code-Lizenzen deiner Rolle: unbegrenzt',
  'role_licenses': 'Code-Lizenzen deiner Rolle',
  'license_users': 'Nutzer',
  'license_open_codes': 'offene Codes',
  'no_chat_data': 'Keine Chatdaten gefunden.',
  'messages': 'Nachrichten',
  'reports': 'Meldungen',
  'delete_subject_chat': 'Fachchat löschen',
  'chat_deleted': 'Chat gelöscht',
  'delete_chat_msg': 'wird inklusive Nachrichten und Bewertungen gelöscht.',
  'reported_messages': 'Gemeldete Nachrichten',
  'no_open_reports': 'Keine offenen Meldungen.',
  'resolve_report': 'Meldung erledigen',
  'report_resolved': 'Meldung erledigt',
  'no_ratings': 'Keine Bewertungen.',
  'edit_admin_points': 'Admin-Punkte bearbeiten',
  'admin_points': 'Admin-Punkte',
  'admin_points_saved': 'Admin-Punkte gespeichert',
  'note': 'Notiz',
  'create_item': 'Artikel erstellen',
  'edit_item': 'Artikel bearbeiten',
  'item_created': 'Artikel erstellt',
  'item_saved': 'Artikel gespeichert',
  'delete_item_q': 'Artikel löschen?',
  'item_deleted': 'Artikel gelöscht',
  'bulk_listing': 'Massen Listung',
  'no_items_entered': 'Keine Artikel eingegeben.',
  'items_created': 'Artikel erstellt',
  'no_shop_items': 'Keine Ladenartikel.',
  'title': 'Titel',
  'description': 'Beschreibung',
  'price_hint': 'Preis-Hinweis',
  'points_price': 'Punktepreis',
  'class_all': 'Klasse (leer = alle Klassen)',
  'sort_order': 'Sortierung',
  'items': 'Artikel',
  'one_item_per_line': 'Ein Artikel pro Zeile',
  'create_contact': 'Kontakt erstellen',
  'edit_contact': 'Kontakt bearbeiten',
  'contact_created': 'Kontakt erstellt',
  'contact_saved': 'Kontakt gespeichert',
  'delete_contact_q': 'Kontakt löschen?',
  'contact_deleted': 'Kontakt gelöscht',
  'no_teacher_contacts': 'Keine Lehrer-Kontakte.',
  'name': 'Name',
  'school': 'Schule',
  'no_school': 'Keine',
  'no_school_set': 'Keine Schule gesetzt',
  'all_schools': 'alle Schulen',
  'add_school': 'Schule hinzufügen',
  'school_name': 'Schulname',
  'school_created': 'Schule angelegt',
  'no_schools': 'Noch keine Schulen.',
  'dev_only': 'Nur fuer Devs.',
  'school_logo': 'Schul-Logo',
  'image_url': 'Bild-URL',
  'logo_saved': 'Logo gespeichert',
  'set_logo_url': 'Logo-URL setzen',
  'remove': 'Entfernen',
  'no_logo': 'Noch kein Schul-Logo gesetzt.',
  'role': 'Rolle',
  'user_role': 'User',
  'no_pro_level': 'Kein Pro-Level',
  'reason_optional': 'Grund (optional)',
  'report_message': 'Nachricht melden',
  'message_reported': 'Nachricht wurde gemeldet.',
  'location': 'Ort',
  'set_location': 'Ort festlegen',
  'appointment': 'Termin',
  'no_appointment_set': 'Kein Termin gesetzt',
  'appointment_ended_label': 'Termin beendet',
  'appointment_running': 'Termin läuft · Raum geschlossen',
  'set_appointment': 'Termin setzen',
  'change_appointment': 'Termin ändern',
  'start_appointment': 'Termin starten',
  'end_appointment': 'Termin beenden',
  'rate': 'Bewerten',
  'change_rating': 'Bewertung ändern',
  'rate_appointment': 'Termin bewerten',
  'rating': 'Bewertung',
  'comment': 'Kommentar',
  'stars5': '5 Sterne',
  'stars4': '4 Sterne',
  'stars3': '3 Sterne',
  'stars2': '2 Sterne',
  'stars1': '1 Stern',
  'chat_title': 'Chat-Titel',
  'group_duration': 'Lerngruppen bleiben bis zum Termin-Ende aktiv.',
  'learn_tip_1': 'Ziel fuer die naechsten 25 Minuten festlegen.',
  'learn_tip_2': 'Eine Frage vorbereiten, bevor du den Chat betrittst.',
  'learn_tip_3': 'Nach jedem Termin drei Stichpunkte sichern.',
  'motivation_1': 'Kleine Schritte zaehlen, wenn du sie regelmaessig machst.',
  'motivation_2': 'Erklaeren zeigt schnell, was du schon kannst.',
  'learn_place_1': 'Bibliothek',
  'learn_place_2': 'Freier Klassenraum',
  'learn_place_3': 'Ruhige Ecke in der Schule',
  'need_comment_local': 'Bei weniger als 4 Sternen ist ein Kommentar nötig.',
  'chat_ended_local': 'Der Termin ist beendet. Der Chat wurde geleert.',
  'all_password_fields': 'Bitte alle Passwortfelder ausfüllen.',
  'password_mismatch': 'Passwörter stimmen nicht überein.',
  'error_prefix': 'Fehler',
  'verified': 'verifiziert',
  'open': 'offen',
  'created': 'Erstellt',
  'stars': 'Sterne',
  'reported_by': 'Gemeldet von',
  'minutes_short': 'Min.',
  'hours_short': 'Std.',
  'medium': 'Mittel',
  'username_short': 'Benutzername zu kurz.',
  'current_password_wrong': 'Aktuelles Passwort stimmt nicht.',
  'ban_reason_too_long': 'Sperrgrund ist zu lang.',
  'username_taken': 'Benutzername ist schon vergeben.',
  'login_invalid': 'Login-Daten stimmen nicht.',
  'bad_invite': 'Einladungscode ist ungültig.',
  'bad_contact_email': 'E-Mail-Adresse ist ungültig.',
  'bad_iserv_email': 'IServ-E-Mail ist ungültig.',
  'invalid_avatar_url': 'Avatar-URL ist ungültig.',
  'notify_no_email': 'Bitte erst eine E-Mail-Adresse eintragen.',
  'invalid_school': 'Schulname ist zu lang.',
  'invalid_logo_url': 'Logo-URL ist ungültig.',
  'invalid_role': 'Rolle ist ungültig.',
  'invalid_limit': 'Code-Lizenzlimit ist ungültig.',
  'code_limit': 'Keine freie Code-Lizenz verfügbar.',
  'invalid_datetime': 'Bitte ein gültiges Datum wählen.',
  'empty_location': 'Bitte einen Ort eingeben.',
  'invalid_location': 'Der Ort ist zu lang.',
  'permission': 'Nur Pros können diesen Termin ändern.',
  'no_appointment_error': 'Es gibt keinen Termin.',
  'not_started': 'Der Termin wurde noch nicht gestartet.',
  'already_ended': 'Der Termin ist schon beendet.',
  'room_closed_error': 'Der Termin läuft schon. Der Raum ist geschlossen.',
  'already_reported': 'Du hast diese Nachricht schon gemeldet.',
  'message_not_found': 'Diese Nachricht gibt es nicht mehr.',
  'own_message': 'Eigene Nachrichten kannst du nicht melden.',
  'reason_too_long': 'Der Meldegrund ist zu lang.',
  'report_not_found': 'Diese Meldung gibt es nicht mehr.',
  'not_ended': 'Der Termin wurde noch nicht beendet.',
  'not_in_room': 'Du bist nicht mehr im Raum.',
  'setup_done': 'Es gibt schon ein Admin-Konto.',
  'auth': 'Bitte neu einloggen.',
  'forbidden': 'Dafür hast du keine Berechtigung.',
};

const _localizedText = {
  'en': {
    'language': 'Language',
    'logout': 'Log out',
    'shop': 'Store',
    'profile': 'Profile',
    'learn': 'Learn',
    'tips': 'Tips',
    'motivation': 'Motivation',
    'learn_places': 'Study places',
    'invite_register': 'Register with code',
    'setup_admin': 'Set admin',
    'create_account': 'Create account',
    'username': 'Username',
    'password': 'Password',
    'confirm_password': 'Confirm password',
    'invite_code': 'Invite code',
    'setup_only': 'Only possible if no admin account exists.',
    'password_short': 'Password too short.',
    'hello': 'Hello',
    'class': 'Class',
    'subject_chat': 'Subject chat',
    'create_chat': 'Create chat',
    'no_chat_open': 'No subject chat is open right now.',
    'continue': 'Continue',
    'room_closed': 'Room closed',
    'join': 'Join',
    'back': 'Back',
    'report': 'Report',
    'write_message': 'Write a message',
    'send': 'Send',
    'points': 'Points',
    'save': 'Save',
    'refresh': 'Refresh',
    'users': 'Users',
    'ratings': 'Ratings',
    'teachers': 'Teachers',
    'schools': 'Schools',
    'licenses': 'Licenses',
    'administration': 'Administration',
    'german': 'German',
    'math': 'Math',
    'english': 'English',
    'biology': 'Biology',
    'spanish': 'Spanish',
    'art': 'Art',
    'store_text': 'View points and buy active offers.',
    'chat_text': 'Noob and medium users can write once a pro is in the room.',
    'admin_text': 'Manage users, invite codes, chats, ratings, and store.',
    'email': 'Email address',
    'avatar': 'Avatar',
    'avatar_url': 'Avatar image URL',
    'iserv_connect': 'Connect IServ',
    'iserv_email': 'IServ email',
    'notify_shop': 'Notify me by email for store purchases',
    'change_password': 'Change password',
    'current_password': 'Current password',
    'new_password': 'New password',
    'confirm_new_password': 'Confirm new password',
    'saved': 'Saved',
    'chat_title': 'Chat title',
    'group_duration': 'Study groups stay active until the appointment ends.',
    'learn_tip_1': 'Set one target for the next 25 minutes.',
    'learn_tip_2': 'Prepare one question before joining a chat.',
    'learn_tip_3': 'Save three notes after every appointment.',
    'motivation_1': 'Small steps count when you repeat them.',
    'motivation_2': 'Explaining shows what you already understand.',
    'learn_place_1': 'Library',
    'learn_place_2': 'Free classroom',
    'learn_place_3': 'Quiet place at school',
  },
  'fr': {
    'language': 'Langue',
    'logout': 'Déconnexion',
    'home': 'Accueil',
    'shop': 'Boutique',
    'profile': 'Profil',
    'login': 'Connexion',
    'invite_register': 'Inscription avec code',
    'setup_admin': 'Définir admin',
    'create_account': 'Créer un compte',
    'username': 'Nom d’utilisateur',
    'password': 'Mot de passe',
    'confirm_password': 'Confirmer le mot de passe',
    'invite_code': 'Code d’invitation',
    'hello': 'Bonjour',
    'class': 'Classe',
    'subject_chat': 'Chat par matière',
    'create_chat': 'Créer un chat',
    'join': 'Rejoindre',
    'back': 'Retour',
    'report': 'Signaler',
    'write_message': 'Écrire un message',
    'send': 'Envoyer',
    'points': 'Points',
    'save': 'Enregistrer',
    'refresh': 'Actualiser',
    'users': 'Utilisateurs',
    'ratings': 'Évaluations',
    'teachers': 'Enseignants',
    'schools': 'Écoles',
    'licenses': 'Licences',
    'administration': 'Administration',
    'german': 'Allemand',
    'math': 'Maths',
    'english': 'Anglais',
    'biology': 'Biologie',
    'spanish': 'Espagnol',
    'art': 'Arts',
    'email': 'Adresse e-mail',
    'change_password': 'Changer le mot de passe',
    'saved': 'Enregistré',
  },
  'es': {
    'language': 'Idioma',
    'logout': 'Cerrar sesión',
    'home': 'Inicio',
    'shop': 'Tienda',
    'profile': 'Perfil',
    'login': 'Iniciar sesión',
    'invite_register': 'Registrarse con código',
    'setup_admin': 'Configurar admin',
    'create_account': 'Crear cuenta',
    'username': 'Usuario',
    'password': 'Contraseña',
    'confirm_password': 'Confirmar contraseña',
    'invite_code': 'Código de invitación',
    'hello': 'Hola',
    'class': 'Clase',
    'subject_chat': 'Chat de asignaturas',
    'create_chat': 'Crear chat',
    'join': 'Unirse',
    'back': 'Atrás',
    'report': 'Reportar',
    'write_message': 'Escribir mensaje',
    'send': 'Enviar',
    'points': 'Puntos',
    'save': 'Guardar',
    'refresh': 'Actualizar',
    'users': 'Usuarios',
    'ratings': 'Valoraciones',
    'teachers': 'Profesores',
    'schools': 'Escuelas',
    'licenses': 'Licencias',
    'administration': 'Administración',
    'german': 'Alemán',
    'math': 'Matemáticas',
    'english': 'Inglés',
    'biology': 'Biología',
    'spanish': 'Español',
    'art': 'Arte',
    'email': 'Correo electrónico',
    'change_password': 'Cambiar contraseña',
    'saved': 'Guardado',
  },
  'el': {'language': 'Γλώσσα', 'logout': 'Αποσύνδεση', 'home': 'Αρχική', 'shop': 'Κατάστημα', 'profile': 'Προφίλ', 'login': 'Σύνδεση', 'invite_register': 'Εγγραφή με κωδικό', 'setup_admin': 'Ορισμός διαχειριστή', 'create_account': 'Δημιουργία λογαριασμού', 'username': 'Όνομα χρήστη', 'password': 'Κωδικός', 'confirm_password': 'Επιβεβαίωση κωδικού', 'hello': 'Γεια', 'save': 'Αποθήκευση'},
  'sq': {'language': 'Gjuha', 'logout': 'Dil', 'home': 'Kryefaqja', 'shop': 'Dyqani', 'profile': 'Profili', 'login': 'Hyrje', 'invite_register': 'Regjistrohu me kod', 'setup_admin': 'Cakto admin', 'create_account': 'Krijo llogari', 'username': 'Përdoruesi', 'password': 'Fjalëkalimi', 'confirm_password': 'Konfirmo fjalëkalimin', 'hello': 'Përshëndetje', 'save': 'Ruaj'},
  'hu': {'language': 'Nyelv', 'logout': 'Kijelentkezés', 'home': 'Kezdőlap', 'shop': 'Bolt', 'profile': 'Profil', 'login': 'Bejelentkezés', 'invite_register': 'Regisztráció kóddal', 'setup_admin': 'Admin beállítása', 'create_account': 'Fiók létrehozása', 'username': 'Felhasználónév', 'password': 'Jelszó', 'confirm_password': 'Jelszó megerősítése', 'hello': 'Szia', 'save': 'Mentés'},
  'fi': {'language': 'Kieli', 'logout': 'Kirjaudu ulos', 'home': 'Etusivu', 'shop': 'Kauppa', 'profile': 'Profiili', 'login': 'Kirjaudu', 'invite_register': 'Rekisteröidy koodilla', 'setup_admin': 'Aseta admin', 'create_account': 'Luo tili', 'username': 'Käyttäjänimi', 'password': 'Salasana', 'confirm_password': 'Vahvista salasana', 'hello': 'Hei', 'save': 'Tallenna'},
  'et': {'language': 'Keel', 'logout': 'Logi välja', 'home': 'Avaleht', 'shop': 'Pood', 'profile': 'Profiil', 'login': 'Logi sisse', 'invite_register': 'Registreeru koodiga', 'setup_admin': 'Määra admin', 'create_account': 'Loo konto', 'username': 'Kasutajanimi', 'password': 'Parool', 'confirm_password': 'Kinnita parool', 'hello': 'Tere', 'save': 'Salvesta'},
  'tr': {'language': 'Dil', 'logout': 'Çıkış', 'home': 'Ana sayfa', 'shop': 'Mağaza', 'profile': 'Profil', 'login': 'Giriş', 'invite_register': 'Kodla kayıt ol', 'setup_admin': 'Admin ayarla', 'create_account': 'Hesap oluştur', 'username': 'Kullanıcı adı', 'password': 'Şifre', 'confirm_password': 'Şifreyi onayla', 'hello': 'Merhaba', 'save': 'Kaydet'},
  'eu': {'language': 'Hizkuntza', 'logout': 'Irten', 'home': 'Hasiera', 'shop': 'Denda', 'profile': 'Profila', 'login': 'Saioa hasi', 'invite_register': 'Erregistratu kodearekin', 'setup_admin': 'Ezarri admina', 'create_account': 'Sortu kontua', 'username': 'Erabiltzailea', 'password': 'Pasahitza', 'confirm_password': 'Berretsi pasahitza', 'hello': 'Kaixo', 'save': 'Gorde'},
  'mt': {'language': 'Lingwa', 'logout': 'Oħroġ', 'home': 'Dar', 'shop': 'Ħanut', 'profile': 'Profil', 'login': 'Idħol', 'invite_register': 'Irreġistra b’kodiċi', 'setup_admin': 'Issettja admin', 'create_account': 'Oħloq kont', 'username': 'Username', 'password': 'Password', 'confirm_password': 'Ikkonferma password', 'hello': 'Bongu', 'save': 'Issejvja'},
  'ga': {'language': 'Teanga', 'logout': 'Logáil amach', 'home': 'Baile', 'shop': 'Siopa', 'profile': 'Próifíl', 'login': 'Logáil isteach', 'invite_register': 'Cláraigh le cód', 'setup_admin': 'Socraigh riarthóir', 'create_account': 'Cruthaigh cuntas', 'username': 'Ainm úsáideora', 'password': 'Pasfhocal', 'confirm_password': 'Deimhnigh pasfhocal', 'hello': 'Dia dhuit', 'save': 'Sábháil'},
  'cy': {'language': 'Iaith', 'logout': 'Allgofnodi', 'home': 'Hafan', 'shop': 'Siop', 'profile': 'Proffil', 'login': 'Mewngofnodi', 'invite_register': 'Cofrestru gyda chod', 'setup_admin': 'Gosod admin', 'create_account': 'Creu cyfrif', 'username': 'Enw defnyddiwr', 'password': 'Cyfrinair', 'confirm_password': 'Cadarnhau cyfrinair', 'hello': 'Helo', 'save': 'Cadw'},
  'pl': {'language': 'Język', 'logout': 'Wyloguj', 'home': 'Start', 'shop': 'Sklep', 'profile': 'Profil', 'login': 'Logowanie', 'invite_register': 'Rejestracja kodem', 'setup_admin': 'Ustaw admina', 'create_account': 'Utwórz konto', 'username': 'Nazwa użytkownika', 'password': 'Hasło', 'confirm_password': 'Potwierdź hasło', 'hello': 'Cześć', 'save': 'Zapisz'},
  'cs': {'language': 'Jazyk', 'logout': 'Odhlásit', 'home': 'Domů', 'shop': 'Obchod', 'profile': 'Profil', 'login': 'Přihlášení', 'invite_register': 'Registrovat kódem', 'setup_admin': 'Nastavit admina', 'create_account': 'Vytvořit účet', 'username': 'Uživatel', 'password': 'Heslo', 'confirm_password': 'Potvrdit heslo', 'hello': 'Ahoj', 'save': 'Uložit'},
  'sk': {'language': 'Jazyk', 'logout': 'Odhlásiť', 'home': 'Domov', 'shop': 'Obchod', 'profile': 'Profil', 'login': 'Prihlásenie', 'invite_register': 'Registrovať kódom', 'setup_admin': 'Nastaviť admina', 'create_account': 'Vytvoriť účet', 'username': 'Používateľ', 'password': 'Heslo', 'confirm_password': 'Potvrdiť heslo', 'hello': 'Ahoj', 'save': 'Uložiť'},
  'uk': {'language': 'Мова', 'logout': 'Вийти', 'home': 'Головна', 'shop': 'Крамниця', 'profile': 'Профіль', 'login': 'Вхід', 'invite_register': 'Реєстрація з кодом', 'setup_admin': 'Налаштувати адміна', 'create_account': 'Створити акаунт', 'username': 'Користувач', 'password': 'Пароль', 'confirm_password': 'Підтвердити пароль', 'hello': 'Привіт', 'save': 'Зберегти'},
  'ru': {'language': 'Язык', 'logout': 'Выйти', 'home': 'Главная', 'shop': 'Магазин', 'profile': 'Профиль', 'login': 'Вход', 'invite_register': 'Регистрация по коду', 'setup_admin': 'Назначить админа', 'create_account': 'Создать аккаунт', 'username': 'Пользователь', 'password': 'Пароль', 'confirm_password': 'Подтвердить пароль', 'hello': 'Привет', 'save': 'Сохранить'},
  'hr': {'language': 'Jezik', 'logout': 'Odjava', 'home': 'Početna', 'shop': 'Trgovina', 'profile': 'Profil', 'login': 'Prijava', 'invite_register': 'Registracija kodom', 'setup_admin': 'Postavi admina', 'create_account': 'Stvori račun', 'username': 'Korisnik', 'password': 'Lozinka', 'confirm_password': 'Potvrdi lozinku', 'hello': 'Bok', 'save': 'Spremi'},
  'sr': {'language': 'Језик', 'logout': 'Одјава', 'home': 'Почетна', 'shop': 'Продавница', 'profile': 'Профил', 'login': 'Пријава', 'invite_register': 'Регистрација кодом', 'setup_admin': 'Постави админа', 'create_account': 'Направи налог', 'username': 'Корисник', 'password': 'Лозинка', 'confirm_password': 'Потврди лозинку', 'hello': 'Здраво', 'save': 'Сачувај'},
  'bg': {'language': 'Език', 'logout': 'Изход', 'home': 'Начало', 'shop': 'Магазин', 'profile': 'Профил', 'login': 'Вход', 'invite_register': 'Регистрация с код', 'setup_admin': 'Задай админ', 'create_account': 'Създай акаунт', 'username': 'Потребител', 'password': 'Парола', 'confirm_password': 'Потвърди парола', 'hello': 'Здравей', 'save': 'Запази'},
  'sl': {'language': 'Jezik', 'logout': 'Odjava', 'home': 'Domov', 'shop': 'Trgovina', 'profile': 'Profil', 'login': 'Prijava', 'invite_register': 'Registracija s kodo', 'setup_admin': 'Nastavi admina', 'create_account': 'Ustvari račun', 'username': 'Uporabnik', 'password': 'Geslo', 'confirm_password': 'Potrdi geslo', 'hello': 'Živjo', 'save': 'Shrani'},
  'pt': {'language': 'Idioma', 'logout': 'Sair', 'home': 'Início', 'shop': 'Loja', 'profile': 'Perfil', 'login': 'Entrar', 'invite_register': 'Registrar com código', 'setup_admin': 'Definir admin', 'create_account': 'Criar conta', 'username': 'Usuário', 'password': 'Senha', 'confirm_password': 'Confirmar senha', 'hello': 'Olá', 'save': 'Salvar'},
  'it': {'language': 'Lingua', 'logout': 'Esci', 'home': 'Home', 'shop': 'Negozio', 'profile': 'Profilo', 'login': 'Accesso', 'invite_register': 'Registrati con codice', 'setup_admin': 'Imposta admin', 'create_account': 'Crea account', 'username': 'Utente', 'password': 'Password', 'confirm_password': 'Conferma password', 'hello': 'Ciao', 'save': 'Salva'},
  'ro': {'language': 'Limbă', 'logout': 'Deconectare', 'home': 'Acasă', 'shop': 'Magazin', 'profile': 'Profil', 'login': 'Autentificare', 'invite_register': 'Înregistrare cu cod', 'setup_admin': 'Setează admin', 'create_account': 'Creează cont', 'username': 'Utilizator', 'password': 'Parolă', 'confirm_password': 'Confirmă parola', 'hello': 'Salut', 'save': 'Salvează'},
  'nl': {'language': 'Taal', 'logout': 'Uitloggen', 'home': 'Home', 'shop': 'Winkel', 'profile': 'Profiel', 'login': 'Inloggen', 'invite_register': 'Registreren met code', 'setup_admin': 'Admin instellen', 'create_account': 'Account maken', 'username': 'Gebruiker', 'password': 'Wachtwoord', 'confirm_password': 'Wachtwoord bevestigen', 'hello': 'Hallo', 'save': 'Opslaan'},
  'sv': {'language': 'Språk', 'logout': 'Logga ut', 'home': 'Hem', 'shop': 'Butik', 'profile': 'Profil', 'login': 'Logga in', 'invite_register': 'Registrera med kod', 'setup_admin': 'Ange admin', 'create_account': 'Skapa konto', 'username': 'Användare', 'password': 'Lösenord', 'confirm_password': 'Bekräfta lösenord', 'hello': 'Hej', 'save': 'Spara'},
  'no': {'language': 'Språk', 'logout': 'Logg ut', 'home': 'Hjem', 'shop': 'Butikk', 'profile': 'Profil', 'login': 'Logg inn', 'invite_register': 'Registrer med kode', 'setup_admin': 'Sett admin', 'create_account': 'Opprett konto', 'username': 'Bruker', 'password': 'Passord', 'confirm_password': 'Bekreft passord', 'hello': 'Hei', 'save': 'Lagre'},
  'da': {'language': 'Sprog', 'logout': 'Log ud', 'home': 'Hjem', 'shop': 'Butik', 'profile': 'Profil', 'login': 'Log ind', 'invite_register': 'Registrer med kode', 'setup_admin': 'Angiv admin', 'create_account': 'Opret konto', 'username': 'Bruger', 'password': 'Adgangskode', 'confirm_password': 'Bekræft adgangskode', 'hello': 'Hej', 'save': 'Gem'},
  'is': {'language': 'Tungumál', 'logout': 'Skrá út', 'home': 'Heim', 'shop': 'Verslun', 'profile': 'Prófíll', 'login': 'Innskráning', 'invite_register': 'Skrá með kóða', 'setup_admin': 'Setja stjórnanda', 'create_account': 'Stofna aðgang', 'username': 'Notandi', 'password': 'Lykilorð', 'confirm_password': 'Staðfesta lykilorð', 'hello': 'Halló', 'save': 'Vista'},
  'de': _baseText,
};

class AppLanguage {
  const AppLanguage(this.code, this.germanName, this.nativeName);

  final String code;
  final String germanName;
  final String nativeName;
}

class AppLanguageController extends ValueNotifier<String> {
  AppLanguageController() : super('de');

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString('app_language');
    if (saved != null && appLanguages.any((lang) => lang.code == saved)) {
      value = saved;
    }
  }

  Future<void> setLanguage(String code) async {
    if (value == code) return;
    value = code;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('app_language', code);
  }
}

final appLanguage = AppLanguageController();

class LanguageScope extends InheritedWidget {
  const LanguageScope({required this.code, required super.child, super.key});

  final String code;

  static LanguageScope of(BuildContext context) {
    return context.dependOnInheritedWidgetOfExactType<LanguageScope>()!;
  }

  String t(String key) {
    return _localizedText[code]?[key] ??
        (code == 'de' ? null : _localizedText['en']?[key]) ??
        _baseText[key] ??
        key;
  }

  @override
  bool updateShouldNotify(LanguageScope oldWidget) => oldWidget.code != code;
}

String tx(BuildContext context, String key) => LanguageScope.of(context).t(key);

class LanguageMenuButton extends StatelessWidget {
  const LanguageMenuButton({super.key});

  @override
  Widget build(BuildContext context) {
    final current = LanguageScope.of(context).code;
    return PopupMenuButton<String>(
      tooltip: tx(context, 'language'),
      icon: const Icon(Icons.language),
      initialValue: current,
      onSelected: appLanguage.setLanguage,
      itemBuilder: (context) => [
        for (final language in appLanguages)
          PopupMenuItem(
            value: language.code,
            child: Row(
              children: [
                SizedBox(
                  width: 34,
                  child: Text(language.code.toUpperCase()),
                ),
                Expanded(child: Text(language.nativeName)),
                if (language.code == current) const Icon(Icons.check, size: 18),
              ],
            ),
          ),
      ],
    );
  }
}

class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  final api = ApiClient(baseUrl: apiBaseUrl);
  UserProfile? user;
  int tab = 0;
  bool loading = true;
  String? error;

  @override
  void initState() {
    super.initState();
    _restoreSession();
  }

  Future<void> _restoreSession() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('api_token');
    if (token == null) {
      setState(() => loading = false);
      return;
    }
    api.token = token;
    try {
      final me = await api.getJson('/api/me');
      setState(() {
        user = UserProfile.fromJson(me);
        loading = false;
      });
    } catch (_) {
      await prefs.remove('api_token');
      setState(() {
        api.token = null;
        loading = false;
      });
    }
  }

  Future<void> _login(String username, String password) async {
    final data = await api.postJson('/api/login', {
      'username': username,
      'password': password,
    });
    await _storeAuth(data);
  }

  Future<void> _redeemInvite(
    String code,
    String username,
    String password,
    String passwordConfirm,
  ) async {
    final data = await api.postJson('/api/invite', {
      'code': code,
      'username': username,
      'password': password,
      'password_confirm': passwordConfirm,
    });
    await _storeAuth(data);
  }

  Future<void> _setupAdmin(
    String username,
    String password,
    String passwordConfirm,
  ) async {
    final data = await api.postJson('/api/setup', {
      'username': username,
      'password': password,
      'password_confirm': passwordConfirm,
    });
    await _storeAuth(data);
  }

  Future<void> _storeAuth(Map<String, dynamic> data) async {
    api.token = data['token']?.toString();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('api_token', api.token!);
    setState(() {
      user = UserProfile.fromJson(data['user'] as Map<String, dynamic>);
      error = null;
    });
  }

  Future<void> _logout() async {
    try {
      await api.postJson('/api/logout', {});
    } catch (_) {
      // Local logout still matters if the server is unreachable.
    }
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('api_token');
    setState(() {
      api.token = null;
      user = null;
      tab = 0;
    });
  }

  Future<void> _refreshMe() async {
    final me = await api.getJson('/api/me');
    setState(() => user = UserProfile.fromJson(me));
  }

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (user == null) {
      return LoginScreen(
        onLogin: _login,
        onInvite: _redeemInvite,
        onSetupAdmin: _setupAdmin,
        error: error,
      );
    }

    final isAdmin =
        user!.role == 'admin' || user!.role == 'dev' || user!.role == 'teacher';
    final pages = [
      DashboardScreen(
        user: user!,
        onOpenChat: () => setState(() => tab = 1),
        onOpenShop: () => setState(() => tab = 2),
        onOpenAdmin: isAdmin ? () => setState(() => tab = 5) : null,
      ),
      ChatScreen(api: api, user: user!),
      ShopScreen(api: api),
      const LearnScreen(),
      SettingsScreen(api: api, user: user!, onSaved: _refreshMe),
      if (isAdmin)
        AdminScreen(
          api: api,
          isDev: user!.role == 'dev',
          adminRole: user!.role,
          adminSchool: user!.school,
          adminClass: user!.className,
          onAppSettingsSaved: _refreshMe,
        ),
    ];
    final selectedTab = tab < pages.length ? tab : 0;

    return Scaffold(
      appBar: AppBar(
        toolbarHeight: 72,
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: Image.asset(
                'docs/assets/benconnect-logo.jpeg',
                width: 48,
                height: 48,
                fit: BoxFit.contain,
              ),
            ),
            const SizedBox(width: 10),
            const Text('benconnect'),
          ],
        ),
        actions: [
          const LanguageMenuButton(),
          UserAvatar(user: user!, radius: 22),
          if (user!.schoolLogoUrl.isNotEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 8),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: Image.network(
                  user!.schoolLogoUrl,
                  width: 60,
                  height: 60,
                  fit: BoxFit.contain,
                  errorBuilder: (context, error, stackTrace) =>
                      const Icon(Icons.image_not_supported_outlined),
                ),
              ),
            ),
          IconButton(
            tooltip: tx(context, 'logout'),
            onPressed: _logout,
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: SafeArea(child: pages[selectedTab]),
      bottomNavigationBar: NavigationBar(
        selectedIndex: selectedTab,
        onDestinationSelected: (value) => setState(() => tab = value),
        destinations: [
          NavigationDestination(
            icon: const Icon(Icons.dashboard_outlined),
            selectedIcon: const Icon(Icons.dashboard),
            label: tx(context, 'home'),
          ),
          NavigationDestination(
            icon: const Icon(Icons.chat_bubble_outline),
            selectedIcon: const Icon(Icons.chat_bubble),
            label: tx(context, 'chat'),
          ),
          NavigationDestination(
            icon: const Icon(Icons.storefront_outlined),
            selectedIcon: const Icon(Icons.storefront),
            label: tx(context, 'shop'),
          ),
          NavigationDestination(
            icon: const Icon(Icons.lightbulb_outline),
            selectedIcon: const Icon(Icons.lightbulb),
            label: tx(context, 'learn'),
          ),
          NavigationDestination(
            icon: const Icon(Icons.settings_outlined),
            selectedIcon: const Icon(Icons.settings),
            label: tx(context, 'profile'),
          ),
          if (isAdmin)
            NavigationDestination(
              icon: const Icon(Icons.admin_panel_settings_outlined),
              selectedIcon: const Icon(Icons.admin_panel_settings),
              label: tx(context, 'admin'),
            ),
        ],
      ),
    );
  }
}

enum AuthMode { login, invite, setup }

class LoginScreen extends StatefulWidget {
  const LoginScreen({
    required this.onLogin,
    required this.onInvite,
    required this.onSetupAdmin,
    this.error,
    super.key,
  });

  final Future<void> Function(String username, String password) onLogin;
  final Future<void> Function(
    String code,
    String username,
    String password,
    String passwordConfirm,
  ) onInvite;
  final Future<void> Function(
    String username,
    String password,
    String passwordConfirm,
  ) onSetupAdmin;
  final String? error;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final username = TextEditingController();
  final password = TextEditingController();
  final passwordConfirm = TextEditingController();
  final inviteCode = TextEditingController();
  AuthMode mode = AuthMode.login;
  bool busy = false;
  String? error;

  @override
  void dispose() {
    username.dispose();
    password.dispose();
    passwordConfirm.dispose();
    inviteCode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final title = switch (mode) {
      AuthMode.login => tx(context, 'login'),
      AuthMode.invite => tx(context, 'invite_register'),
      AuthMode.setup => tx(context, 'setup_admin'),
    };
    final action = switch (mode) {
      AuthMode.login => tx(context, 'login'),
      AuthMode.invite => tx(context, 'create_account'),
      AuthMode.setup => tx(context, 'setup_admin'),
    };
    final icon = switch (mode) {
      AuthMode.login => Icons.login,
      AuthMode.invite => Icons.card_giftcard,
      AuthMode.setup => Icons.admin_panel_settings,
    };

    return Scaffold(
      appBar: AppBar(
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: Image.asset(
                'docs/assets/benconnect-logo.jpeg',
                width: 48,
                height: 48,
                fit: BoxFit.contain,
              ),
            ),
            const SizedBox(width: 10),
            const Text('benconnect'),
          ],
        ),
        actions: const [LanguageMenuButton()],
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: ListView(
            padding: const EdgeInsets.all(20),
            shrinkWrap: true,
            children: [
              Text(title, style: Theme.of(context).textTheme.headlineMedium),
              const SizedBox(height: 20),
              SegmentedButton<AuthMode>(
                segments: [
                  ButtonSegment(
                    value: AuthMode.login,
                    icon: const Icon(Icons.login),
                    label: Text(tx(context, 'login')),
                  ),
                  ButtonSegment(
                    value: AuthMode.invite,
                    icon: const Icon(Icons.card_giftcard),
                    label: Text(tx(context, 'codes')),
                  ),
                  ButtonSegment(
                    value: AuthMode.setup,
                    icon: const Icon(Icons.admin_panel_settings),
                    label: Text(tx(context, 'admin')),
                  ),
                ],
                selected: {mode},
                onSelectionChanged: busy
                    ? null
                    : (set) => setState(() {
                          mode = set.first;
                          error = null;
                        }),
              ),
              if (mode == AuthMode.setup) ...[
                const SizedBox(height: 12),
                Text(
                  tx(context, 'setup_only'),
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
              if (mode == AuthMode.invite) ...[
                const SizedBox(height: 12),
                TextField(
                  controller: inviteCode,
                  textInputAction: TextInputAction.next,
                  decoration:
                      InputDecoration(labelText: tx(context, 'invite_code')),
                ),
              ],
              const SizedBox(height: 12),
              TextField(
                controller: username,
                textInputAction: TextInputAction.next,
                decoration: InputDecoration(labelText: tx(context, 'username')),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: password,
                obscureText: true,
                onSubmitted: (_) => _submit(),
                decoration: InputDecoration(labelText: tx(context, 'password')),
              ),
              if (mode != AuthMode.login) ...[
                const SizedBox(height: 12),
                TextField(
                  controller: passwordConfirm,
                  obscureText: true,
                  onSubmitted: (_) => _submit(),
                  decoration: InputDecoration(
                    labelText: tx(context, 'confirm_password'),
                  ),
                ),
              ],
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: busy ? null : _submit,
                icon: busy
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : Icon(icon),
                label: Text(action),
              ),
              if (error != null || widget.error != null) ...[
                const SizedBox(height: 12),
                Text(
                  error ?? widget.error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              const SizedBox(height: 16),
              Text(
                '${tx(context, 'api')}: $apiBaseUrl',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _submit() async {
    final usernameText = username.text.trim();
    final passwordText = password.text;
    final passwordConfirmText = passwordConfirm.text;
    final inviteCodeText = inviteCode.text.trim();

    if (passwordText.length < 6) {
      setState(() => error = tx(context, 'password_short'));
      return;
    }

    setState(() {
      busy = true;
      error = null;
    });
    try {
      if (mode == AuthMode.login) {
        await widget.onLogin(usernameText, passwordText);
      } else if (mode == AuthMode.invite) {
        await widget.onInvite(
          inviteCodeText,
          usernameText,
          passwordText,
          passwordConfirmText,
        );
      } else {
        await widget.onSetupAdmin(
          usernameText,
          passwordText,
          passwordConfirmText,
        );
      }
    } catch (ex) {
      setState(() => error = friendlyError(context, ex));
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }
}

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({
    required this.user,
    required this.onOpenChat,
    required this.onOpenShop,
    this.onOpenAdmin,
    super.key,
  });

  final UserProfile user;
  final VoidCallback onOpenChat;
  final VoidCallback onOpenShop;
  final VoidCallback? onOpenAdmin;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            UserAvatar(user: user, radius: 28),
            const SizedBox(width: 12),
            Expanded(
              child: Text('${tx(context, 'hello')}, ${displayName(user.username)}',
                  style: Theme.of(context).textTheme.headlineSmall),
            ),
            if (user.isStaff) ...[
              const SizedBox(width: 8),
              Icon(user.roleIcon,
                  size: 26, color: Theme.of(context).colorScheme.primary),
            ],
          ],
        ),
        const SizedBox(height: 16),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            LevelChip(label: tx(context, 'german'), value: user.levelGerman),
            LevelChip(label: tx(context, 'math'), value: user.levelMath),
            LevelChip(label: tx(context, 'english'), value: user.levelEnglish),
            LevelChip(label: tx(context, 'biology'), value: user.levelBiology),
            LevelChip(label: tx(context, 'pgw'), value: user.levelPgw),
            LevelChip(label: tx(context, 'spanish'), value: user.levelSpanish),
            LevelChip(label: tx(context, 'art'), value: user.levelArt),
            if (user.className.isNotEmpty)
              Chip(label: Text('${tx(context, 'class')} ${user.className}')),
          ],
        ),
        const SizedBox(height: 20),
        InfoCard(
          icon: Icons.chat_bubble_outline,
          title: tx(context, 'subject_chat'),
          text: tx(context, 'chat_text'),
          onTap: onOpenChat,
        ),
        const SizedBox(height: 12),
        InfoCard(
          icon: Icons.storefront_outlined,
          title: tx(context, 'shop'),
          text: tx(context, 'store_text'),
          onTap: onOpenShop,
        ),
        if (onOpenAdmin != null) ...[
          const SizedBox(height: 12),
          InfoCard(
            icon: Icons.admin_panel_settings_outlined,
            title: tx(context, 'administration'),
            text: tx(context, 'admin_text'),
            onTap: onOpenAdmin!,
          ),
        ],
      ],
    );
  }
}

String displayName(String value) {
  final trimmed = value.trim();
  if (trimmed.isEmpty) return '';
  return trimmed[0].toUpperCase() + trimmed.substring(1);
}

class UserAvatar extends StatelessWidget {
  const UserAvatar({required this.user, this.radius = 20, super.key});

  final UserProfile user;
  final double radius;

  @override
  Widget build(BuildContext context) {
    final initials = displayName(user.username).isEmpty
        ? '?'
        : displayName(user.username)[0];
    if (user.avatarUrl.isNotEmpty) {
      return CircleAvatar(
        radius: radius,
        backgroundImage: NetworkImage(user.avatarUrl),
        onBackgroundImageError: (_, __) {},
        child: const SizedBox.shrink(),
      );
    }
    return CircleAvatar(
      radius: radius,
      child: Text(initials),
    );
  }
}

class LevelChip extends StatelessWidget {
  const LevelChip({required this.label, required this.value, super.key});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Chip(
      avatar: const Icon(Icons.school, size: 18),
      label: Text('$label: ${levelLabel(value)}'),
    );
  }
}

class InfoCard extends StatelessWidget {
  const InfoCard({
    required this.icon,
    required this.title,
    required this.text,
    required this.onTap,
    super.key,
  });

  final IconData icon;
  final String title;
  final String text;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        onTap: onTap,
        leading: Icon(icon),
        title: Text(title),
        subtitle: Text(text),
        trailing: const Icon(Icons.chevron_right),
      ),
    );
  }
}

class ChatScreen extends StatefulWidget {
  const ChatScreen({required this.api, required this.user, super.key});

  final ApiClient api;
  final UserProfile user;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  List<dynamic> rooms = const [];
  List<dynamic> creatableRooms = const [];
  List<dynamic> messages = const [];
  Map<String, dynamic>? appointment;
  String? subject;
  String? subjectLabel;
  String? error;
  int since = 0;
  Timer? timer;
  final input = TextEditingController();

  @override
  void initState() {
    super.initState();
    _loadRooms();
    timer = Timer.periodic(const Duration(seconds: 3), (_) {
      if (subject == null) {
        _loadRooms(silent: true);
      } else {
        _loadMessages(silent: true);
        _loadAppointment(silent: true);
      }
    });
  }

  @override
  void dispose() {
    timer?.cancel();
    input.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (subject != null) return _chatPanel(context);
    return RefreshIndicator(
      onRefresh: _loadRooms,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(tx(context, 'subject_chat'),
              style: Theme.of(context).textTheme.headlineSmall),
          if (error != null) ErrorBanner(error!),
          if (creatableRooms.isNotEmpty) ...[
            const SizedBox(height: 12),
            Align(
              alignment: Alignment.centerLeft,
              child: FilledButton.icon(
                onPressed: _createChatRoom,
                icon: const Icon(Icons.add_comment_outlined),
                label: Text(tx(context, 'create_chat')),
              ),
            ),
          ],
          const SizedBox(height: 12),
          if (rooms.isEmpty && creatableRooms.isEmpty)
            Text(tx(context, 'no_chat_open')),
          for (final room in rooms) _roomCard(room as Map<String, dynamic>),
        ],
      ),
    );
  }

  Widget _roomCard(Map<String, dynamic> room) {
    final members = (room['members'] as List? ?? const []);
    final canJoin = room['can_join'] == true;
    final joinBlock = room['join_block']?.toString();
    final appointmentText = room['appointment']?.toString() ?? '';
    final locationText = room['location']?.toString() ?? '';
    final buttonLabel = room['you_in'] == true
        ? tx(context, 'continue')
        : joinBlock == 'started'
            ? tx(context, 'room_closed')
            : tx(context, 'join');
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('${tx(context, 'chat_title')}: ${room['label']}',
                  style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 6),
              Text(
                '${room['count_non_pro']} / ${room['max']} ohne Pro, '
                '${room['count_pro']} Pro online',
              ),
              const SizedBox(height: 4),
              Text(
                tx(context, 'group_duration'),
                style: Theme.of(context).textTheme.bodySmall,
              ),
              if (appointmentText.isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(
                  locationText.isEmpty
                      ? '${tx(context, 'appointment')}: $appointmentText'
                      : '${tx(context, 'appointment')}: $appointmentText · ${tx(context, 'location')}: $locationText',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
              if (members.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Wrap(
                    spacing: 8,
                    runSpacing: 4,
                    children: [
                      for (final raw in members)
                        _memberLabel(raw as Map<String, dynamic>),
                    ],
                  ),
                ),
              const SizedBox(height: 12),
              FilledButton.icon(
                onPressed: canJoin ? () => _join(room) : null,
                icon: const Icon(Icons.meeting_room),
                label: Text(buttonLabel),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _memberLabel(Map<String, dynamic> member) {
    final verified = member['pro_verified'] == true;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          '${displayName(member['username']?.toString() ?? '')} (${levelLabel(member['level'])})',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        if (verified) ...[
          const SizedBox(width: 3),
          Icon(
            Icons.verified,
            size: 15,
            color: Theme.of(context).colorScheme.primary,
          ),
        ],
      ],
    );
  }

  Widget _chatPanel(BuildContext context) {
    return Column(
      children: [
        Material(
          color: Theme.of(context).colorScheme.surface,
          child: ListTile(
            leading: IconButton(
              tooltip: tx(context, 'back'),
              onPressed: _leave,
              icon: const Icon(Icons.arrow_back),
            ),
            title: Text('${tx(context, 'chat_title')}: ${subjectLabel ?? 'Chat'}'),
            subtitle: error == null ? null : Text(error!),
          ),
        ),
        _appointmentPanel(context),
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: messages.length,
            itemBuilder: (context, index) {
              final msg = messages[index] as Map<String, dynamic>;
              final own = msg['user_id'] == widget.user.userId;
              final role = msg['role']?.toString();
              final senderIcon =
                  iconForRole(role ?? (own ? widget.user.role : null));
              final proVerified = msg['pro_verified'] == true;
              return Align(
                alignment: own ? Alignment.centerRight : Alignment.centerLeft,
                child: Card(
                  color: own
                      ? Theme.of(context).colorScheme.primaryContainer
                      : null,
                  child: Padding(
                    padding: const EdgeInsets.all(10),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              '${displayName(msg['username']?.toString() ?? '')} · ${msg['created_at']}',
                              style: Theme.of(context).textTheme.labelSmall,
                            ),
                            if (senderIcon != null) ...[
                              const SizedBox(width: 6),
                              Icon(
                                senderIcon,
                                size: 16,
                                color: Theme.of(context).colorScheme.primary,
                              ),
                            ],
                            if (proVerified) ...[
                              const SizedBox(width: 6),
                              Icon(
                                Icons.verified,
                                size: 16,
                                color: Theme.of(context).colorScheme.primary,
                              ),
                            ],
                          ],
                        ),
                        const SizedBox(height: 4),
                        Text(msg['body']?.toString() ?? ''),
                        if (!own)
                          Align(
                            alignment: Alignment.centerRight,
                            child: TextButton.icon(
                              onPressed: () => _reportMessage(msg),
                              icon: const Icon(Icons.flag_outlined, size: 18),
                              label: Text(tx(context, 'report')),
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
              );
            },
          ),
        ),
        SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: input,
                    maxLength: 500,
                    decoration: InputDecoration(
                      counterText: '',
                      hintText: tx(context, 'write_message'),
                    ),
                    onSubmitted: (_) => _send(),
                  ),
                ),
                const SizedBox(width: 8),
                IconButton.filled(
                  tooltip: tx(context, 'send'),
                  onPressed: _send,
                  icon: const Icon(Icons.send),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _appointmentPanel(BuildContext context) {
    final active = subject;
    if (active == null) return const SizedBox.shrink();
    final data = appointment;
    final appointmentText = data?['appointment']?.toString() ?? '';
    final locationText = data?['location']?.toString() ?? '';
    final started = data?['started'] == true;
    final ended = data?['ended'] == true;
    final yourRating = data?['your_rating'] as Map<String, dynamic>?;
    final isPro = widget.user.levelFor(active) == 'pro';
    final ratingAvg = data?['rating_avg'];
    final ratingAvgNum = ratingAvg is num ? ratingAvg : null;
    final ratingAvgText =
        ratingAvgNum != null ? ' · Avg ${ratingAvgNum.toStringAsFixed(1)}' : '';
    return Material(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.event, size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    appointmentText.isEmpty
                        ? tx(context, 'no_appointment_set')
                        : locationText.isEmpty
                            ? '${tx(context, 'appointment')}: $appointmentText'
                            : '${tx(context, 'appointment')}: $appointmentText · ${tx(context, 'location')}: $locationText',
                  ),
                ),
              ],
            ),
            if (ended) ...[
              const SizedBox(height: 6),
              Text(
                tx(context, 'appointment_ended_label'),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ] else if (started) ...[
              const SizedBox(height: 6),
              Text(
                tx(context, 'appointment_running'),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
            if (isPro && data?['rating_count'] != null) ...[
              const SizedBox(height: 6),
              Row(
                children: [
                  Text(
                    '${tx(context, 'ratings')}: ${data?['rating_count']}$ratingAvgText',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  if (ratingAvgNum != null) ...[
                    const SizedBox(width: 8),
                    StarRatingDisplay(value: ratingAvgNum.round()),
                  ],
                ],
              ),
            ],
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                if (isPro && !started && !ended)
                  OutlinedButton.icon(
                    onPressed: _setAppointment,
                    icon: const Icon(Icons.edit_calendar),
                    label: Text(
                      appointmentText.isEmpty
                          ? tx(context, 'set_appointment')
                          : tx(context, 'change_appointment'),
                    ),
                  ),
                if (isPro && appointmentText.isNotEmpty && !started && !ended)
                  FilledButton.icon(
                    onPressed: _startAppointment,
                    icon: const Icon(Icons.play_arrow),
                    label: Text(tx(context, 'start_appointment')),
                  ),
                if (isPro && started && !ended)
                  FilledButton.icon(
                    onPressed: _endAppointment,
                    icon: const Icon(Icons.flag),
                    label: Text(tx(context, 'end_appointment')),
                  ),
                if (isPro && ended)
                  FilledButton.icon(
                    onPressed: () => _rateAppointment(yourRating),
                    icon: const Icon(Icons.star),
                    label: Text(
                      yourRating == null ? tx(context, 'rate') : tx(context, 'change_rating'),
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _loadRooms({bool silent = false}) async {
    try {
      final data = await widget.api.getJson('/api/chat/rooms');
      setState(() {
        rooms = data['rooms'] as List? ?? const [];
        creatableRooms = data['creatable'] as List? ?? const [];
        if (!silent) error = null;
      });
    } catch (ex) {
      if (!silent) setState(() => error = ex.toString());
    }
  }

  Future<void> _join(Map<String, dynamic> room) async {
    try {
      await widget.api.postJson('/api/chat/join', {'subject': room['subject']});
      setState(() {
        subject = room['subject'].toString();
        subjectLabel = room['label'].toString();
        messages = const [];
        since = 0;
        error = null;
      });
      await _loadMessages();
      await _loadAppointment();
    } catch (ex) {
      setState(() => error = friendlyError(context, ex));
    }
  }

  Future<void> _createChatRoom() async {
    Map<String, dynamic>? room;
    if (creatableRooms.length == 1) {
      room = creatableRooms.first as Map<String, dynamic>;
    } else {
      room = await showDialog<Map<String, dynamic>>(
        context: context,
        builder: (context) => SimpleDialog(
          title: Text(tx(context, 'create_chat')),
          children: [
            for (final raw in creatableRooms)
              Builder(
                builder: (context) {
                  final roomItem = raw as Map<String, dynamic>;
                  return SimpleDialogOption(
                    onPressed: () => Navigator.of(context).pop(roomItem),
                    child: Text(roomItem['label'].toString()),
                  );
                },
              ),
          ],
        ),
      );
    }
    if (room == null) return;
    await _join(room);
  }

  Future<void> _leave() async {
    final leaving = subject;
    setState(() {
      subject = null;
      subjectLabel = null;
      messages = const [];
      appointment = null;
      since = 0;
    });
    if (leaving != null) {
      try {
        await widget.api.postJson('/api/chat/leave', {'subject': leaving});
      } catch (_) {}
    }
    await _loadRooms(silent: true);
  }

  Future<void> _loadMessages({bool silent = false}) async {
    final active = subject;
    if (active == null) return;
    try {
      final data = await widget.api.getJson('/api/chat/messages', {
        'subject': active,
        'since': since.toString(),
      });
      final next = data['messages'] as List? ?? const [];
      setState(() {
        messages = [...messages, ...next];
        for (final item in next) {
          final id = (item as Map<String, dynamic>)['id'] as int;
          if (id > since) since = id;
        }
        if (!silent) error = null;
      });
    } catch (ex) {
      if (ex is ApiException && ex.code == 'appointment_ended') {
        setState(() {
          messages = const [];
          since = 0;
          if (!silent) error = friendlyError(context, ex);
        });
      } else if (!silent) {
        setState(() => error = ex.toString());
      }
    }
  }

  Future<void> _send() async {
    final active = subject;
    final body = input.text.trim();
    if (active == null || body.isEmpty) return;
    if (appointment?['ended'] == true) {
      input.clear();
      setState(() => error = tx(context, 'chat_ended_local'));
      return;
    }
    input.clear();
    try {
      await widget.api.postJson('/api/chat/send', {
        'subject': active,
        'body': body,
      });
      await _loadMessages(silent: true);
    } catch (ex) {
      setState(() => error = friendlyError(context, ex));
    }
  }

  Future<void> _reportMessage(Map<String, dynamic> message) async {
    final reason = await showDialog<String>(
      context: context,
      builder: (context) => TextEntryDialog(
        title: tx(context, 'report_message'),
        label: tx(context, 'reason_optional'),
        initialValue: '',
        obscure: false,
        maxLength: 300,
      ),
    );
    if (reason == null) return;
    try {
      await widget.api.postJson('/api/chat/report-message', {
        'message_id': message['id'],
        'reason': reason.trim(),
      });
      setState(() => error = tx(context, 'message_reported'));
    } catch (ex) {
      setState(() => error = friendlyError(context, ex));
    }
  }

  Future<void> _loadAppointment({bool silent = false}) async {
    final active = subject;
    if (active == null) return;
    try {
      final data = await widget.api.getJson('/api/chat/appointment', {
        'subject': active,
      });
      setState(() {
        appointment = data;
        if (data['ended'] == true) {
          messages = const [];
          since = 0;
        }
        if (!silent) error = null;
      });
    } catch (ex) {
      if (!silent) setState(() => error = ex.toString());
    }
  }

  Future<void> _setAppointment() async {
    final active = subject;
    if (active == null) return;
    final now = DateTime.now();
    final date = await showDatePicker(
      context: context,
      initialDate: now,
      firstDate: DateTime(now.year, now.month, now.day),
      lastDate: DateTime(now.year + 2),
    );
    if (date == null) return;
    if (!mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(now.add(const Duration(hours: 1))),
    );
    if (time == null) return;
    final value =
        '${date.year}-${_two(date.month)}-${_two(date.day)} ${_two(time.hour)}:${_two(time.minute)}';
    if (!mounted) return;
    final location = await _appointmentLocationDialog();
    if (location == null) return;
    try {
      await widget.api.postJson('/api/chat/appointment', {
        'subject': active,
        'appointment': value,
        'location': location,
      });
      await _loadAppointment();
      await _loadRooms(silent: true);
    } catch (ex) {
      setState(() => error = friendlyError(context, ex));
    }
  }

  Future<String?> _appointmentLocationDialog() async {
    final controller = TextEditingController();
    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(tx(context, 'set_location')),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLength: 120,
          decoration: InputDecoration(labelText: tx(context, 'location')),
          textInputAction: TextInputAction.done,
          onSubmitted: (_) {
            final value = controller.text.trim();
            if (value.isNotEmpty) Navigator.pop(context, value);
          },
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text(tx(context, 'cancel')),
          ),
          FilledButton(
            onPressed: () {
              final value = controller.text.trim();
              if (value.isNotEmpty) Navigator.pop(context, value);
            },
            child: Text(tx(context, 'save')),
          ),
        ],
      ),
    );
    controller.dispose();
    return result?.trim().isEmpty == true ? null : result?.trim();
  }

  Future<void> _endAppointment() async {
    final active = subject;
    if (active == null) return;
    try {
      await widget.api.postJson('/api/chat/appointment/end', {
        'subject': active,
      });
      setState(() {
        messages = const [];
        since = 0;
      });
      await _loadAppointment();
    } catch (ex) {
      setState(() => error = friendlyError(context, ex));
    }
  }

  Future<void> _startAppointment() async {
    final active = subject;
    if (active == null) return;
    try {
      await widget.api.postJson('/api/chat/appointment/start', {
        'subject': active,
      });
      await _loadAppointment();
      await _loadRooms(silent: true);
    } catch (ex) {
      setState(() => error = friendlyError(context, ex));
    }
  }

  Future<void> _rateAppointment(Map<String, dynamic>? current) async {
    final active = subject;
    if (active == null) return;
    final result = await _ratingDialog(current);
    if (result == null) return;
    if (result.rating < 4 && result.comment.trim().isEmpty) {
      setState(
          () => error = tx(context, 'need_comment_local'));
      return;
    }
    try {
      await widget.api.postJson('/api/chat/appointment/rate', {
        'subject': active,
        'rating': result.rating,
        'comment': result.comment.trim(),
      });
      await _loadAppointment();
    } catch (ex) {
      setState(() => error = friendlyError(context, ex));
    }
  }

  Future<RatingEdit?> _ratingDialog(Map<String, dynamic>? current) async {
    var rating = int.tryParse(current?['rating']?.toString() ?? '') ?? 5;
    final comment = TextEditingController(
      text: current?['comment']?.toString() ?? '',
    );
    final result = await showDialog<RatingEdit>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text(tx(context, 'rate_appointment')),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              StarRatingInput(
                value: rating,
                onChanged: (value) => setDialogState(() => rating = value),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: comment,
                maxLines: 3,
                decoration: InputDecoration(labelText: tx(context, 'comment')),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text(tx(context, 'cancel')),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(
                context,
                RatingEdit(rating, comment.text),
              ),
              child: Text(tx(context, 'save')),
            ),
          ],
        ),
      ),
    );
    comment.dispose();
    return result;
  }
}

class RatingEdit {
  const RatingEdit(this.rating, this.comment);

  final int rating;
  final String comment;
}

class StarRatingInput extends StatelessWidget {
  const StarRatingInput({
    required this.value,
    required this.onChanged,
    super.key,
  });

  final int value;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        for (var i = 1; i <= 5; i++)
          IconButton(
            tooltip: '$i ${tx(context, 'stars')}',
            onPressed: () => onChanged(i),
            icon: Icon(i <= value ? Icons.star : Icons.star_border),
            color: Theme.of(context).colorScheme.primary,
          ),
      ],
    );
  }
}

class StarRatingDisplay extends StatelessWidget {
  const StarRatingDisplay({required this.value, super.key});

  final int value;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 1; i <= 5; i++)
          Icon(
            i <= value ? Icons.star : Icons.star_border,
            size: 16,
            color: Theme.of(context).colorScheme.primary,
          ),
      ],
    );
  }
}

String _two(int value) => value.toString().padLeft(2, '0');

class LearnScreen extends StatelessWidget {
  const LearnScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      child: Column(
        children: [
          Material(
            color: Theme.of(context).colorScheme.surface,
            child: TabBar(
              tabs: [
                Tab(icon: const Icon(Icons.tips_and_updates), text: tx(context, 'tips')),
                Tab(icon: const Icon(Icons.bolt), text: tx(context, 'motivation')),
                Tab(icon: const Icon(Icons.place), text: tx(context, 'learn_places')),
              ],
            ),
          ),
          Expanded(
            child: TabBarView(
              children: [
                _LearningList(
                  icon: Icons.check_circle_outline,
                  items: [
                    tx(context, 'learn_tip_1'),
                    tx(context, 'learn_tip_2'),
                    tx(context, 'learn_tip_3'),
                  ],
                ),
                _LearningList(
                  icon: Icons.star_outline,
                  items: [
                    tx(context, 'motivation_1'),
                    tx(context, 'motivation_2'),
                  ],
                ),
                _LearningList(
                  icon: Icons.location_on_outlined,
                  items: [
                    tx(context, 'learn_place_1'),
                    tx(context, 'learn_place_2'),
                    tx(context, 'learn_place_3'),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _LearningList extends StatelessWidget {
  const _LearningList({required this.icon, required this.items});

  final IconData icon;
  final List<String> items;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        for (final item in items)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Card(
              child: ListTile(
                leading: Icon(icon),
                title: Text(item),
              ),
            ),
          ),
      ],
    );
  }
}

class ShopScreen extends StatefulWidget {
  const ShopScreen({required this.api, super.key});

  final ApiClient api;

  @override
  State<ShopScreen> createState() => _ShopScreenState();
}

class _ShopScreenState extends State<ShopScreen> {
  List<dynamic> items = const [];
  int points = 0;
  String? error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(tx(context, 'shop'), style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 8),
          Text('${tx(context, 'points')}: $points'),
          if (error != null) ErrorBanner(error!),
          const SizedBox(height: 12),
          for (final item in items) _shopItem(item as Map<String, dynamic>),
        ],
      ),
    );
  }

  Widget _shopItem(Map<String, dynamic> item) {
    final cost = item['points_price'] as int? ?? 0;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Card(
        child: ListTile(
          title: Text(item['title']?.toString() ?? ''),
          subtitle: Text(item['description']?.toString() ?? ''),
          trailing: cost > 0
              ? FilledButton(
                  onPressed: points >= cost ? () => _buy(item) : null,
                  child: Text('$cost P'),
                )
              : const Icon(Icons.info_outline),
        ),
      ),
    );
  }

  Future<void> _load() async {
    try {
      final data = await widget.api.getJson('/api/shop');
      setState(() {
        items = data['items'] as List? ?? const [];
        points = data['points_balance'] as int? ?? 0;
        error = null;
      });
    } catch (ex) {
      setState(() => error = ex.toString());
    }
  }

  Future<void> _buy(Map<String, dynamic> item) async {
    try {
      final data = await widget.api.postJson('/api/shop/purchase', {
        'item_id': item['id'],
      });
      setState(() {
        points = data['points_balance'] as int? ?? points;
        error = data['mail_notice']?.toString();
      });
    } catch (ex) {
      setState(() => error = ex.toString());
    }
  }
}

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({
    required this.api,
    required this.user,
    required this.onSaved,
    super.key,
  });

  final ApiClient api;
  final UserProfile user;
  final Future<void> Function() onSaved;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late String german;
  late String math;
  late String english;
  late String biology;
  late String pgw;
  late String spanish;
  late String art;
  late final TextEditingController email;
  late final TextEditingController avatarUrl;
  late final TextEditingController iservEmail;
  late final TextEditingController currentPassword;
  late final TextEditingController newPassword;
  late final TextEditingController newPasswordConfirm;
  late bool notify;
  bool busy = false;
  String? status;

  @override
  void initState() {
    super.initState();
    german = widget.user.levelGerman;
    math = widget.user.levelMath;
    english = widget.user.levelEnglish;
    biology = widget.user.levelBiology;
    pgw = widget.user.levelPgw;
    spanish = widget.user.levelSpanish;
    art = widget.user.levelArt;
    email = TextEditingController(text: widget.user.contactEmail);
    avatarUrl = TextEditingController(text: widget.user.avatarUrl);
    iservEmail = TextEditingController(text: widget.user.iservEmail);
    currentPassword = TextEditingController();
    newPassword = TextEditingController();
    newPasswordConfirm = TextEditingController();
    notify = widget.user.notifyLadenEmail;
  }

  @override
  void dispose() {
    email.dispose();
    avatarUrl.dispose();
    iservEmail.dispose();
    currentPassword.dispose();
    newPassword.dispose();
    newPasswordConfirm.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(tx(context, 'profile'), style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 16),
        Row(
          children: [
            UserAvatar(user: widget.user, radius: 32),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                displayName(widget.user.username),
                style: Theme.of(context).textTheme.titleLarge,
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        Text(tx(context, 'avatar'),
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 12),
        TextField(
          controller: avatarUrl,
          keyboardType: TextInputType.url,
          decoration: InputDecoration(labelText: tx(context, 'avatar_url')),
        ),
        const SizedBox(height: 12),
        Text(tx(context, 'iserv_connect'),
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 12),
        TextField(
          controller: iservEmail,
          keyboardType: TextInputType.emailAddress,
          decoration: InputDecoration(labelText: tx(context, 'iserv_email')),
        ),
        const SizedBox(height: 16),
        LevelSelector(
          label: tx(context, 'german'),
          value: german,
          onChanged: (v) => setState(() => german = v),
        ),
        LevelSelector(
          label: tx(context, 'math'),
          value: math,
          onChanged: (v) => setState(() => math = v),
        ),
        LevelSelector(
          label: tx(context, 'english'),
          value: english,
          onChanged: (v) => setState(() => english = v),
        ),
        LevelSelector(
          label: tx(context, 'biology'),
          value: biology,
          onChanged: (v) => setState(() => biology = v),
        ),
        LevelSelector(
          label: tx(context, 'pgw'),
          value: pgw,
          onChanged: (v) => setState(() => pgw = v),
        ),
        LevelSelector(
          label: tx(context, 'spanish'),
          value: spanish,
          onChanged: (v) => setState(() => spanish = v),
        ),
        LevelSelector(
          label: tx(context, 'art'),
          value: art,
          onChanged: (v) => setState(() => art = v),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: email,
          keyboardType: TextInputType.emailAddress,
          decoration: InputDecoration(labelText: tx(context, 'email')),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          value: notify,
          onChanged: (value) => setState(() => notify = value),
          title: Text(tx(context, 'notify_shop')),
        ),
        const SizedBox(height: 16),
        Text(tx(context, 'change_password'),
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 12),
        TextField(
          controller: currentPassword,
          obscureText: true,
          decoration: InputDecoration(labelText: tx(context, 'current_password')),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: newPassword,
          obscureText: true,
          decoration: InputDecoration(labelText: tx(context, 'new_password')),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: newPasswordConfirm,
          obscureText: true,
          decoration: InputDecoration(
            labelText: tx(context, 'confirm_new_password'),
          ),
        ),
        const SizedBox(height: 8),
        FilledButton.icon(
          onPressed: busy ? null : _save,
          icon: const Icon(Icons.save),
          label: Text(tx(context, 'save')),
        ),
        if (status != null) ...[
          const SizedBox(height: 12),
          Text(status!),
        ],
      ],
    );
  }

  Future<void> _save() async {
    final currentPasswordText = currentPassword.text;
    final newPasswordText = newPassword.text;
    final newPasswordConfirmText = newPasswordConfirm.text;
    final wantsPasswordChange = currentPasswordText.isNotEmpty ||
        newPasswordText.isNotEmpty ||
        newPasswordConfirmText.isNotEmpty;

    if (wantsPasswordChange) {
      if (currentPasswordText.isEmpty ||
          newPasswordText.isEmpty ||
          newPasswordConfirmText.isEmpty) {
        setState(() => status = tx(context, 'all_password_fields'));
        return;
      }
      if (newPasswordText.length < 6) {
        setState(() => status = tx(context, 'password_short'));
        return;
      }
      if (newPasswordText != newPasswordConfirmText) {
        setState(() => status = tx(context, 'password_mismatch'));
        return;
      }
    }

    setState(() {
      busy = true;
      status = null;
    });
    try {
      await widget.api.postJson('/api/profile', {
        'level_german': german,
        'level_math': math,
        'level_english': english,
        'level_biology': biology,
        'level_pgw': pgw,
        'level_spanish': spanish,
        'level_art': art,
        'contact_email': email.text.trim(),
        'notify_laden_email': notify,
        'avatar_url': avatarUrl.text.trim(),
        'iserv_email': iservEmail.text.trim(),
        if (wantsPasswordChange) ...{
          'current_password': currentPasswordText,
          'new_password': newPasswordText,
          'new_password_confirm': newPasswordConfirmText,
        },
      });
      await widget.onSaved();
      if (wantsPasswordChange) {
        currentPassword.clear();
        newPassword.clear();
        newPasswordConfirm.clear();
      }
      setState(() => status = tx(context, 'saved'));
    } catch (ex) {
      setState(() => status = friendlyError(context, ex));
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }
}

enum AdminSection {
  users,
  codes,
  chats,
  ratings,
  shop,
  teachers,
  logo,
  schools
}

class AdminScreen extends StatefulWidget {
  const AdminScreen({
    required this.api,
    required this.isDev,
    required this.adminRole,
    required this.adminSchool,
    required this.adminClass,
    required this.onAppSettingsSaved,
    super.key,
  });

  final ApiClient api;
  final bool isDev;
  final String adminRole;
  final String adminSchool;
  final String adminClass;
  final Future<void> Function() onAppSettingsSaved;

  @override
  State<AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends State<AdminScreen> {
  AdminSection section = AdminSection.users;
  bool loading = false;
  String? status;
  List<dynamic> users = const [];
  List<dynamic> codes = const [];
  List<dynamic> chats = const [];
  List<dynamic> chatReports = const [];
  List<dynamic> ratings = const [];
  List<dynamic> shopItems = const [];
  List<dynamic> teachers = const [];
  List<String> schools = const [];
  Map<String, dynamic> inviteCodeLimits = const {};
  String schoolLogoUrl = '';
  String selectedLogoSchool = '';
  String selectedLicenseSchool = '';

  @override
  void initState() {
    super.initState();
    _loadSchools();
    _load();
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  tx(context, 'administration'),
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
              ),
              IconButton(
                tooltip: tx(context, 'refresh'),
                onPressed: loading ? null : _load,
                icon: const Icon(Icons.refresh),
              ),
            ],
          ),
          const SizedBox(height: 12),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: SegmentedButton<AdminSection>(
              segments: [
                ButtonSegment(
                  value: AdminSection.users,
                  icon: const Icon(Icons.people),
                  label: Text(tx(context, 'users')),
                ),
                ButtonSegment(
                  value: AdminSection.codes,
                  icon: const Icon(Icons.vpn_key),
                  label: Text(tx(context, 'codes')),
                ),
                ButtonSegment(
                  value: AdminSection.chats,
                  icon: const Icon(Icons.forum),
                  label: Text(tx(context, 'chats')),
                ),
                ButtonSegment(
                  value: AdminSection.ratings,
                  icon: const Icon(Icons.star),
                  label: Text(tx(context, 'ratings')),
                ),
                ButtonSegment(
                  value: AdminSection.shop,
                  icon: const Icon(Icons.storefront),
                  label: Text(tx(context, 'shop')),
                ),
                ButtonSegment(
                  value: AdminSection.teachers,
                  icon: const Icon(Icons.alternate_email),
                  label: Text(tx(context, 'teachers')),
                ),
                ButtonSegment(
                  value: AdminSection.logo,
                  icon: const Icon(Icons.image_outlined),
                  label: Text(tx(context, 'logo')),
                ),
                if (widget.isDev)
                  ButtonSegment(
                    value: AdminSection.schools,
                    icon: const Icon(Icons.school_outlined),
                    label: Text(tx(context, 'schools')),
                  ),
              ],
              selected: {section},
              onSelectionChanged: loading
                  ? null
                  : (set) {
                      setState(() {
                        section = set.first;
                        status = null;
                      });
                      _load();
                    },
            ),
          ),
          if (loading) ...[
            const SizedBox(height: 16),
            const LinearProgressIndicator(),
          ],
          if (status != null) ...[
            const SizedBox(height: 12),
            Text(status!),
          ],
          const SizedBox(height: 16),
          _sectionBody(),
        ],
      ),
    );
  }

  Widget _sectionBody() {
    return switch (section) {
      AdminSection.users => _usersBody(),
      AdminSection.codes => _codesBody(),
      AdminSection.chats => _chatsBody(),
      AdminSection.ratings => _ratingsBody(),
      AdminSection.shop => _shopBody(),
      AdminSection.teachers => _teachersBody(),
      AdminSection.logo => _logoBody(),
      AdminSection.schools => _schoolsBody(),
    };
  }

  Widget _usersBody() {
    if (users.isEmpty && !loading) return Text(tx(context, 'no_users'));
    return Column(
      children: [
        for (final raw in users)
          AdminCard(
            title: raw['username']?.toString() ?? '',
            subtitle: _userSubtitle(raw as Map<String, dynamic>),
            leading: raw['role'] == 'admin'
                ? Icons.admin_panel_settings
                : raw['role'] == 'teacher'
                    ? Icons.school
                    : Icons.person_outline,
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  tooltip: tx(context, 'set_password'),
                  onPressed: () => _changePassword(raw),
                  icon: const Icon(Icons.password),
                ),
                if (widget.isDev)
                  IconButton(
                    tooltip: tx(context, 'edit_role_school'),
                    onPressed: () => _editUserAccess(raw),
                    icon: const Icon(Icons.manage_accounts_outlined),
                  ),
                if (widget.adminRole == 'admin' || widget.adminRole == 'dev')
                  IconButton(
                    tooltip: tx(context, 'set_class'),
                    onPressed: () => _setUserClass(raw),
                    icon: const Icon(Icons.class_outlined),
                  ),
                if (_hasProLevel(raw))
                  IconButton(
                    tooltip: tx(context, 'verify_pros'),
                    onPressed: () => _verifyPros(raw),
                    icon: const Icon(Icons.verified_outlined),
                  ),
                IconButton(
                  tooltip:
                      raw['banned'] == true ? tx(context, 'unban') : tx(context, 'ban'),
                  onPressed: () => _setBanned(raw),
                  icon: Icon(
                    raw['banned'] == true
                        ? Icons.lock_open
                        : Icons.block_outlined,
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }

  Widget _codesBody() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(_inviteLicenseText()),
        const SizedBox(height: 12),
        Align(
          alignment: Alignment.centerLeft,
          child: Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              FilledButton.icon(
                onPressed: loading ? null : _createInviteCode,
                icon: const Icon(Icons.add),
                label: Text(tx(context, 'create_code')),
              ),
              if (widget.isDev)
                OutlinedButton.icon(
                  onPressed: loading ? null : _editInviteCodeLimits,
                  icon: const Icon(Icons.key_outlined),
                  label: Text(tx(context, 'licenses')),
                ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        if (codes.isEmpty && !loading) Text(tx(context, 'no_open_codes')),
        for (final raw in codes)
          AdminCard(
            title: raw['code']?.toString() ?? '',
            subtitle: _codeSubtitle(raw as Map<String, dynamic>),
            leading: Icons.vpn_key_outlined,
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  tooltip: tx(context, 'copy_code'),
                  onPressed: () => _copyCode(raw['code']?.toString() ?? ''),
                  icon: const Icon(Icons.copy),
                ),
                IconButton(
                  tooltip: tx(context, 'delete_code'),
                  onPressed: () => _deleteInviteCode(raw),
                  icon: const Icon(Icons.delete_outline),
                ),
              ],
            ),
          ),
      ],
    );
  }

  Widget _chatsBody() {
    if (chats.isEmpty && !loading) {
      return Text(tx(context, 'no_chat_data'));
    }
    return Column(
      children: [
        for (final raw in chats)
          AdminCard(
            title: raw['label']?.toString() ?? raw['subject']?.toString() ?? '',
            subtitle:
                '${raw['message_count'] ?? 0} ${tx(context, 'messages')} · ${raw['rating_count'] ?? 0} ${tx(context, 'ratings')} · ${raw['report_count'] ?? 0} ${tx(context, 'reports')}',
            leading: Icons.forum_outlined,
            trailing: IconButton(
              tooltip: tx(context, 'delete_subject_chat'),
              onPressed: () => _deleteChat(raw as Map<String, dynamic>),
              icon: const Icon(Icons.delete_outline),
            ),
          ),
        const SizedBox(height: 8),
        Align(
          alignment: Alignment.centerLeft,
          child: Text(
            tx(context, 'reported_messages'),
            style: Theme.of(context).textTheme.titleMedium,
          ),
        ),
        const SizedBox(height: 8),
        if (chatReports.isEmpty && !loading)
          Align(
            alignment: Alignment.centerLeft,
            child: Text(tx(context, 'no_open_reports')),
          ),
        for (final raw in chatReports)
          AdminCard(
            title:
                '${raw['subject_label'] ?? raw['subject']} · ${raw['reported_username']}',
            subtitle: _reportSubtitle(raw as Map<String, dynamic>),
            leading: Icons.flag_outlined,
            trailing: IconButton(
              tooltip: tx(context, 'resolve_report'),
              onPressed: () => _resolveReport(raw),
              icon: const Icon(Icons.check_circle_outline),
            ),
          ),
      ],
    );
  }

  Widget _ratingsBody() {
    if (ratings.isEmpty && !loading) return Text(tx(context, 'no_ratings'));
    return Column(
      children: [
        for (final raw in ratings)
          AdminCard(
            title:
                '${raw['subject_label'] ?? raw['subject']} · ${raw['username']}',
            subtitle: _ratingSubtitle(raw as Map<String, dynamic>),
            leading: Icons.star_outline,
            trailing: IconButton(
              tooltip: tx(context, 'edit_admin_points'),
              onPressed: () => _editRating(raw),
              icon: const Icon(Icons.edit_outlined),
            ),
          ),
      ],
    );
  }

  Widget _shopBody() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            FilledButton.icon(
              onPressed: loading ? null : () => _editShopItem(),
              icon: const Icon(Icons.add),
              label: Text(tx(context, 'create_item')),
            ),
            OutlinedButton.icon(
              onPressed: loading ? null : _bulkCreateShopItems,
              icon: const Icon(Icons.playlist_add),
              label: Text(tx(context, 'bulk_listing')),
            ),
          ],
        ),
        const SizedBox(height: 12),
        if (shopItems.isEmpty && !loading) Text(tx(context, 'no_shop_items')),
        for (final raw in shopItems)
          AdminCard(
            title: raw['title']?.toString() ?? '',
            subtitle: _shopSubtitle(raw as Map<String, dynamic>),
            leading: Icons.local_offer_outlined,
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  tooltip: tx(context, 'edit'),
                  onPressed: () => _editShopItem(raw),
                  icon: const Icon(Icons.edit_outlined),
                ),
                IconButton(
                  tooltip: tx(context, 'delete'),
                  onPressed: () => _deleteShopItem(raw),
                  icon: const Icon(Icons.delete_outline),
                ),
              ],
            ),
          ),
      ],
    );
  }

  Widget _teachersBody() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Align(
          alignment: Alignment.centerLeft,
          child: FilledButton.icon(
            onPressed: loading ? null : () => _editTeacher(),
            icon: const Icon(Icons.add),
            label: Text(tx(context, 'create_contact')),
          ),
        ),
        const SizedBox(height: 12),
        if (teachers.isEmpty && !loading) Text(tx(context, 'no_teacher_contacts')),
        for (final raw in teachers)
          AdminCard(
            title: raw['email']?.toString() ?? '',
            subtitle: _teacherSubtitle(raw as Map<String, dynamic>),
            leading: Icons.alternate_email,
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  tooltip: tx(context, 'edit'),
                  onPressed: () => _editTeacher(raw),
                  icon: const Icon(Icons.edit_outlined),
                ),
                IconButton(
                  tooltip: tx(context, 'delete'),
                  onPressed: () => _deleteTeacher(raw),
                  icon: const Icon(Icons.delete_outline),
                ),
              ],
            ),
          ),
      ],
    );
  }

  Widget _logoBody() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (widget.isDev) ...[
          DropdownButtonFormField<String>(
            value: selectedLogoSchool.isEmpty ? null : selectedLogoSchool,
            decoration: InputDecoration(labelText: tx(context, 'school')),
            items: [
              for (final school in schools)
                DropdownMenuItem(value: school, child: Text(school)),
            ],
            onChanged: loading
                ? null
                : (value) {
                    setState(() {
                      selectedLogoSchool = value ?? '';
                      schoolLogoUrl = '';
                    });
                    _load();
                  },
          ),
          const SizedBox(height: 16),
        ],
        if (schoolLogoUrl.isNotEmpty) ...[
          Align(
            alignment: Alignment.centerLeft,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: Image.network(
                schoolLogoUrl,
                width: 144,
                height: 144,
                fit: BoxFit.contain,
                errorBuilder: (context, error, stackTrace) =>
                    const Icon(Icons.image_not_supported_outlined, size: 48),
              ),
            ),
          ),
          const SizedBox(height: 12),
          SelectableText(schoolLogoUrl),
          const SizedBox(height: 12),
        ] else
          Text(tx(context, 'no_logo')),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            FilledButton.icon(
              onPressed: loading ? null : _editLogo,
              icon: const Icon(Icons.edit_outlined),
              label: Text(tx(context, 'set_logo_url')),
            ),
            OutlinedButton.icon(
              onPressed:
                  loading || schoolLogoUrl.isEmpty ? null : () => _saveLogo(''),
              icon: const Icon(Icons.delete_outline),
              label: Text(tx(context, 'remove')),
            ),
          ],
        ),
      ],
    );
  }

  Widget _schoolsBody() {
    if (!widget.isDev) return Text(tx(context, 'dev_only'));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Align(
          alignment: Alignment.centerLeft,
          child: FilledButton.icon(
            onPressed: loading ? null : _createSchool,
            icon: const Icon(Icons.add),
            label: Text(tx(context, 'add_school')),
          ),
        ),
        const SizedBox(height: 12),
        if (schools.isEmpty) Text(tx(context, 'no_schools')),
        for (final school in schools)
          AdminCard(
            title: school,
            subtitle: tx(context, 'school'),
            leading: Icons.school_outlined,
          ),
      ],
    );
  }

  String _userSubtitle(Map<String, dynamic> user) {
    final proText = _proVerificationSummary(user);
    final parts = <String>[
      user['role']?.toString() ?? 'user',
      if ((user['school']?.toString() ?? '').isNotEmpty)
        user['school'].toString(),
      if ((user['class_name']?.toString() ?? '').isNotEmpty)
        "${tx(context, 'class')} ${user['class_name']}",
      if (proText.isNotEmpty) proText,
      user['banned'] == true ? tx(context, 'ban') : tx(context, 'active'),
    ];
    return parts.join(' · ');
  }

  bool _hasProLevel(Map<String, dynamic> user) {
    return user['level_german'] == 'pro' ||
        user['level_math'] == 'pro' ||
        user['level_english'] == 'pro' ||
        user['level_biology'] == 'pro' ||
        user['level_pgw'] == 'pro' ||
        user['level_spanish'] == 'pro' ||
        user['level_art'] == 'pro';
  }

  String _proVerificationSummary(Map<String, dynamic> user) {
    final items = <String>[];
    void add(String label, String levelKey, String verifiedKey) {
      if (user[levelKey] == 'pro') {
        items.add('$label ${user[verifiedKey] == true ? tx(context, 'verified') : tx(context, 'open')}');
      }
    }

    add(tx(context, 'german'), 'level_german', 'pro_verified_german');
    add(tx(context, 'math'), 'level_math', 'pro_verified_math');
    add(tx(context, 'english'), 'level_english', 'pro_verified_english');
    add(tx(context, 'biology'), 'level_biology', 'pro_verified_biology');
    add(tx(context, 'pgw'), 'level_pgw', 'pro_verified_pgw');
    add(tx(context, 'spanish'), 'level_spanish', 'pro_verified_spanish');
    add(tx(context, 'art'), 'level_art', 'pro_verified_art');
    return items.join(', ');
  }

  String _codeSubtitle(Map<String, dynamic> code) {
    final school = code['school']?.toString() ?? '';
    final role = code['role']?.toString() ?? 'user';
    final createdAt = code['created_at']?.toString() ?? '';
    final schoolText = school.isEmpty ? tx(context, 'no_school') : school;
    return '${tx(context, 'school')}: $schoolText · ${tx(context, 'role')}: $role\n${tx(context, 'created')}: $createdAt';
  }

  String _inviteLicenseText() {
    int intValue(Object? value) =>
        value is int ? value : int.tryParse(value?.toString() ?? '') ?? 0;

    final current = inviteCodeLimits['current'] as Map? ?? const {};
    final limit = intValue(current['limit']);
    final active = intValue(current['active']);
    final users = intValue(current['users']);
    final codes = intValue(current['codes']);
    final school = inviteCodeLimits['school']?.toString() ??
        current['school']?.toString() ??
        '';
    final prefix = widget.isDev && school.isNotEmpty
        ? '${tx(context, 'license_pool')}: $school'
        : tx(context, 'role_licenses');
    if (limit == 0) return '$prefix: unbegrenzt';
    return '$prefix: $active / $limit '
        '${tx(context, 'occupied')} ($users ${tx(context, 'license_users')}, '
        '$codes ${tx(context, 'license_open_codes')})';
  }

  String _ratingSubtitle(Map<String, dynamic> rating) {
    final duration = _durationLabel(rating['duration_seconds']);
    final startedAt = rating['started_at']?.toString() ?? '';
    final endedAt = rating['ended_at']?.toString() ?? '';
    return '${rating['rating']}/5 ${tx(context, 'stars')} · ${rating['comment'] ?? ''}'
        '${startedAt.isEmpty ? '' : '\nStart: $startedAt'}'
        '${endedAt.isEmpty ? '' : '\nEnde: $endedAt'}'
        '${duration.isEmpty ? '' : '\nDauer: $duration'}'
        '\n${tx(context, 'admin_points')}: ${rating['admin_points'] ?? 0} · ${rating['admin_note'] ?? ''}';
  }

  String _reportSubtitle(Map<String, dynamic> report) {
    final reason = report['reason']?.toString() ?? '';
    final className = report['reported_class_name']?.toString() ?? '';
    return '"${report['body'] ?? ''}"'
        '\n${tx(context, 'reported_by')} ${report['reporter_username'] ?? ''}'
        '${reason.isEmpty ? '' : '\n${tx(context, 'ban_reason')}: $reason'}'
        '${className.isEmpty ? '' : '\n${tx(context, 'class')}: $className'}'
        '\n${report['created_at'] ?? ''}';
  }

  String _durationLabel(Object? value) {
    final seconds =
        value is int ? value : int.tryParse(value?.toString() ?? '');
    if (seconds == null || seconds < 0) return '';
    final minutes = (seconds / 60).round();
    if (minutes < 60) return '$minutes ${tx(context, 'minutes_short')}';
    final hours = minutes ~/ 60;
    final rest = minutes % 60;
    return rest == 0 ? '$hours ${tx(context, 'hours_short')}' : '$hours ${tx(context, 'hours_short')} $rest ${tx(context, 'minutes_short')}';
  }

  String _shopSubtitle(Map<String, dynamic> item) {
    final school = item['school']?.toString() ?? '';
    final target = school.isEmpty ? tx(context, 'all_schools') : school;
    final state = item['active'] == true ? tx(context, 'active') : tx(context, 'inactive');
    final description = item['description']?.toString() ?? '';
    return '${item['points_price'] ?? 0} ${tx(context, 'points')} · $state · $target\n$description';
  }

  String _teacherSubtitle(Map<String, dynamic> teacher) {
    final parts = <String>[
      if ((teacher['display_name']?.toString() ?? '').isNotEmpty)
        teacher['display_name'].toString(),
      if ((teacher['school']?.toString() ?? '').isNotEmpty)
        teacher['school'].toString(),
      teacher['active'] == true ? tx(context, 'active') : tx(context, 'inactive'),
    ];
    return parts.join(' · ');
  }

  Future<void> _load() async {
    setState(() {
      loading = true;
      status = null;
    });
    try {
      final data = switch (section) {
        AdminSection.users => await widget.api.getJson('/api/admin/users'),
        AdminSection.codes =>
          await widget.api.getJson('/api/admin/invite-codes'),
        AdminSection.chats => await widget.api.getJson('/api/admin/chats'),
        AdminSection.ratings => await widget.api.getJson('/api/admin/ratings'),
        AdminSection.shop => await widget.api.getJson('/api/admin/shop'),
        AdminSection.teachers =>
          await widget.api.getJson('/api/admin/teachers'),
        AdminSection.logo => await widget.api.getJson(
            '/api/admin/app-settings',
            widget.isDev && selectedLogoSchool.isNotEmpty
                ? {'school': selectedLogoSchool}
                : null,
          ),
        AdminSection.schools => await widget.api.getJson('/api/admin/schools'),
      };
      final limitsData = section == AdminSection.codes
          ? await widget.api.getJson(
              '/api/admin/invite-code-limits',
              widget.isDev && selectedLicenseSchool.isNotEmpty
                  ? {'school': selectedLicenseSchool}
                  : null,
            )
          : null;
      final reportsData = section == AdminSection.chats
          ? await widget.api.getJson('/api/admin/chat-reports')
          : null;
      if (!mounted) return;
      setState(() {
        switch (section) {
          case AdminSection.users:
            users = data['users'] as List? ?? const [];
            break;
          case AdminSection.codes:
            codes = data['codes'] as List? ?? const [];
            inviteCodeLimits = limitsData ?? const {};
            break;
          case AdminSection.chats:
            chats = data['chats'] as List? ?? const [];
            chatReports = reportsData?['reports'] as List? ?? const [];
            break;
          case AdminSection.ratings:
            ratings = data['ratings'] as List? ?? const [];
            break;
          case AdminSection.shop:
            shopItems = data['items'] as List? ?? const [];
            break;
          case AdminSection.teachers:
            teachers = data['teachers'] as List? ?? const [];
            break;
          case AdminSection.logo:
            schoolLogoUrl = data['school_logo_url']?.toString() ?? '';
            selectedLogoSchool =
                data['school']?.toString() ?? selectedLogoSchool;
            break;
          case AdminSection.schools:
            schools = (data['schools'] as List? ?? const [])
                .map((item) => item.toString())
                .toList();
            break;
        }
      });
    } catch (ex) {
      if (mounted) setState(() => status = '${tx(context, 'error_prefix')}: $ex');
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _loadSchools() async {
    try {
      final data = await widget.api.getJson('/api/admin/schools');
      if (!mounted) return;
      setState(() {
        schools = (data['schools'] as List? ?? const [])
            .map((item) => item.toString())
            .toList();
        if (widget.isDev && selectedLogoSchool.isEmpty && schools.isNotEmpty) {
          selectedLogoSchool = schools.first;
        }
      });
    } catch (_) {}
  }

  Future<void> _run(String success, Future<void> Function() action) async {
    setState(() {
      loading = true;
      status = null;
    });
    try {
      await action();
      await _load();
      if (mounted) setState(() => status = success);
    } catch (ex) {
      if (mounted) setState(() => status = '${tx(context, 'error_prefix')}: $ex');
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _changePassword(Map<String, dynamic> user) async {
    final password = await _textDialog(
      title: tx(context, 'set_password'),
      label: tx(context, 'new_password'),
      obscure: true,
    );
    if (password == null || password.isEmpty) return;
    await _run(tx(context, 'password_saved'), () async {
      await widget.api.postJson('/api/admin/users/password', {
        'user_id': user['id'],
        'password': password,
      });
    });
  }

  Future<void> _setBanned(Map<String, dynamic> user) async {
    final ban = user['banned'] != true;
    String? message;
    if (ban) {
      message = await _textDialog(
        title: tx(context, 'ban_user'),
        label: tx(context, 'ban_reason'),
        initialValue: user['banned_message']?.toString() ?? '',
        maxLength: 500,
      );
      if (message == null) return;
      if (message.trim().isEmpty) {
        setState(() => status = tx(context, 'ban_reason_required'));
        return;
      }
    } else {
      final ok = await _confirm(
        tx(context, 'unban_user_q'),
        user['username']?.toString() ?? '',
      );
      if (!ok) return;
    }
    await _run(ban ? tx(context, 'user_banned') : tx(context, 'user_unbanned'), () async {
      await widget.api.postJson('/api/admin/users/ban', {
        'user_id': user['id'],
        'ban': ban,
        if (ban) 'message': message!.trim(),
      });
    });
  }

  Future<void> _editUserAccess(Map<String, dynamic> user) async {
    await _loadSchools();
    final result = await _userAccessDialog(user);
    if (result == null) return;
    await _run(tx(context, 'user_saved'), () async {
      await widget.api.putJson('/api/admin/users/${user['id']}', result);
    });
  }

  Future<void> _setUserClass(Map<String, dynamic> user) async {
    final nextClass = await _textDialog(
      title: tx(context, 'set_class'),
      label: tx(context, 'class'),
      initialValue: user['class_name']?.toString() ?? '',
      maxLength: 20,
    );
    if (nextClass == null) return;
    await _run(tx(context, 'class_saved'), () async {
      await widget.api.postJson('/api/admin/users/class', {
        'user_id': user['id'],
        'class_name': nextClass.trim(),
      });
    });
  }

  Future<void> _verifyPros(Map<String, dynamic> user) async {
    final result = await _proVerificationDialog(user);
    if (result == null) return;
    await _run(tx(context, 'pro_verification_saved'), () async {
      await widget.api.postJson('/api/admin/users/pro-verification', {
        'user_id': user['id'],
        ...result,
      });
    });
  }

  Future<void> _createInviteCode() async {
    await _loadSchools();
    final result = await _inviteCodeDialog();
    if (result == null) return;
    await _run(tx(context, 'code_created'), () async {
      await widget.api.postJson('/api/admin/invite-codes', result);
    });
  }

  Future<void> _editInviteCodeLimits() async {
    final currentSchool = inviteCodeLimits['school']?.toString() ??
        selectedLicenseSchool;
    final school = await _textDialog(
      title: tx(context, 'teacher_code_licenses'),
      label: tx(context, 'school'),
      initialValue: currentSchool,
    );
    if (school == null) return;
    final limitInitial = (inviteCodeLimits['school_limit'] ??
            (inviteCodeLimits['current'] as Map?)?['limit'] ??
            0)
        .toString();
    final limit = await _textDialog(
      title: tx(context, 'admin_code_licenses'),
      label: tx(context, 'unlimited_zero'),
      initialValue: limitInitial,
    );
    if (limit == null) return;
    final limitValue = int.tryParse(limit.trim());
    if (limitValue == null || limitValue < 0) {
      setState(() => status = tx(context, 'positive_numbers'));
      return;
    }
    selectedLicenseSchool = school.trim();
    await _run(tx(context, 'code_licenses_saved'), () async {
      await widget.api.postJson('/api/admin/invite-code-limits', {
        'school': selectedLicenseSchool,
        'school_limit': limitValue,
      });
    });
  }

  Future<void> _copyCode(String code) async {
    if (code.isEmpty) return;
    await Clipboard.setData(ClipboardData(text: code));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(tx(context, 'code_copied'))),
    );
  }

  Future<void> _deleteInviteCode(Map<String, dynamic> code) async {
    final value = code['code']?.toString() ?? '';
    if (value.isEmpty) return;
    final ok = await _confirm(
      tx(context, 'delete_invite_code_q'),
      '$value ${tx(context, 'delete_invite_code_msg')}',
    );
    if (!ok) return;
    await _run(tx(context, 'code_deleted'), () async {
      await widget.api.deleteJson(
        '/api/admin/invite-codes/${Uri.encodeComponent(value)}',
      );
    });
  }

  Future<void> _editLogo() async {
    await _loadSchools();
    final value = await _textDialog(
      title: tx(context, 'school_logo'),
      label: tx(context, 'image_url'),
      initialValue: schoolLogoUrl,
      maxLength: 1000,
    );
    if (value == null) return;
    await _saveLogo(value.trim());
  }

  Future<void> _saveLogo(String url) async {
    await _run(tx(context, 'logo_saved'), () async {
      await widget.api.postJson('/api/admin/app-settings', {
        'school_logo_url': url,
        if (widget.isDev) 'school': selectedLogoSchool,
      });
    });
    await widget.onAppSettingsSaved();
  }

  Future<void> _createSchool() async {
    final name = await _textDialog(
      title: tx(context, 'add_school'),
      label: tx(context, 'school_name'),
      maxLength: 120,
    );
    if (name == null || name.trim().isEmpty) return;
    await _run(tx(context, 'school_created'), () async {
      await widget.api.postJson('/api/admin/schools', {'name': name.trim()});
    });
    await _loadSchools();
  }

  Future<void> _deleteChat(Map<String, dynamic> chat) async {
    final ok = await _confirm(
      tx(context, 'delete_subject_chat'),
      '${chat['label']} ${tx(context, 'delete_chat_msg')}',
    );
    if (!ok) return;
    await _run(tx(context, 'chat_deleted'), () async {
      await widget.api.deleteJson(
        '/api/admin/delete_chat/${Uri.encodeComponent(chat['subject'].toString())}',
      );
    });
  }

  Future<void> _resolveReport(Map<String, dynamic> report) async {
    await _run(tx(context, 'report_resolved'), () async {
      await widget.api.postJson(
        '/api/admin/chat-reports/${report['id']}/resolve',
        {},
      );
    });
  }

  Future<void> _editRating(Map<String, dynamic> rating) async {
    final result = await _scoreDialog(rating);
    if (result == null) return;
    await _run(tx(context, 'admin_points_saved'), () async {
      await widget.api.putJson('/api/admin/subject-score', {
        'subject': rating['subject'],
        'user_id': rating['user_id'],
        'points': result.points,
        'note': result.note,
      });
    });
  }

  String _defaultShopSchool() {
    final ownSchool = widget.adminSchool.trim();
    if (ownSchool.isNotEmpty) return ownSchool;
    if (!widget.isDev && schools.length == 1) return schools.first;
    return '';
  }

  void _ensureKnownSchool(String school) {
    if (school.isNotEmpty && !schools.contains(school)) {
      schools = [...schools, school];
    }
  }

  Widget _schoolControl({
    required String school,
    required ValueChanged<String> onChanged,
  }) {
    if (!widget.isDev) {
      final label = school.trim().isEmpty ? tx(context, 'no_school_set') : school;
      return InputDecorator(
        decoration: InputDecoration(labelText: tx(context, 'school')),
        child: Text(label),
      );
    }
    return DropdownButtonFormField<String>(
      value: school,
      decoration: InputDecoration(labelText: tx(context, 'school')),
      items: [
        DropdownMenuItem(value: '', child: Text(tx(context, 'no_school'))),
        for (final value in schools)
          DropdownMenuItem(value: value, child: Text(value)),
      ],
      onChanged: (value) {
        onChanged(value ?? '');
      },
    );
  }

  Future<void> _editShopItem([Map<String, dynamic>? item]) async {
    await _loadSchools();
    final result = await _shopDialog(item);
    if (result == null) return;
    await _run(item == null ? tx(context, 'item_created') : tx(context, 'item_saved'),
        () async {
      if (item == null) {
        await widget.api.postJson('/api/admin/shop', result);
      } else {
        await widget.api.putJson('/api/admin/shop/${item['id']}', result);
      }
    });
  }

  Future<void> _bulkCreateShopItems() async {
    await _loadSchools();
    final result = await _bulkShopDialog();
    if (result == null) return;

    final titles = (result['titles'] as List<String>? ?? const [])
        .map((title) => title.trim())
        .where((title) => title.isNotEmpty)
        .toList();
    if (titles.isEmpty) {
      setState(() => status = tx(context, 'no_items_entered'));
      return;
    }

    await _run('${titles.length} ${tx(context, 'items_created')}', () async {
      for (final title in titles) {
        await widget.api.postJson('/api/admin/shop', {
          'title': title,
          'description': '',
          'price_hint': result['price_hint'],
          'points_price': result['points_price'],
          'school': result['school'],
          'class_name': result['class_name'],
          'sort_order': 0,
          'active': result['active'],
        });
      }
    });
  }

  Future<void> _deleteShopItem(Map<String, dynamic> item) async {
    final ok =
        await _confirm(tx(context, 'delete_item_q'), item['title']?.toString() ?? '');
    if (!ok) return;
    await _run(tx(context, 'item_deleted'), () async {
      await widget.api.deleteJson('/api/admin/shop/${item['id']}');
    });
  }

  Future<void> _editTeacher([Map<String, dynamic>? teacher]) async {
    await _loadSchools();
    final result = await _teacherDialog(teacher);
    if (result == null) return;
    await _run(
      teacher == null ? tx(context, 'contact_created') : tx(context, 'contact_saved'),
      () async {
        if (teacher == null) {
          await widget.api.postJson('/api/admin/teachers', result);
        } else {
          await widget.api
              .putJson('/api/admin/teachers/${teacher['id']}', result);
        }
      },
    );
  }

  Future<void> _deleteTeacher(Map<String, dynamic> teacher) async {
    final ok = await _confirm(
      tx(context, 'delete_contact_q'),
      teacher['email']?.toString() ?? '',
    );
    if (!ok) return;
    await _run(tx(context, 'contact_deleted'), () async {
      await widget.api.deleteJson('/api/admin/teachers/${teacher['id']}');
    });
  }

  Future<bool> _confirm(String title, String message) async {
    return await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: Text(title),
            content: Text(message),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: Text(tx(context, 'cancel')),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(context, true),
                child: Text(tx(context, 'ok')),
              ),
            ],
          ),
        ) ??
        false;
  }

  Future<String?> _textDialog({
    required String title,
    required String label,
    String initialValue = '',
    bool obscure = false,
    int? maxLength,
  }) async {
    final result = await showDialog<String>(
      context: context,
      builder: (context) => TextEntryDialog(
        title: title,
        label: label,
        initialValue: initialValue,
        obscure: obscure,
        maxLength: maxLength,
      ),
    );
    return result?.trim();
  }

  Future<ScoreEdit?> _scoreDialog(Map<String, dynamic> rating) async {
    final points = TextEditingController(
      text: (rating['admin_points'] ?? 0).toString(),
    );
    final note =
        TextEditingController(text: rating['admin_note']?.toString() ?? '');
    final result = await showDialog<ScoreEdit>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(tx(context, 'admin_points')),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: points,
              keyboardType: TextInputType.number,
              decoration: InputDecoration(labelText: tx(context, 'points')),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: note,
              maxLength: 500,
              decoration: InputDecoration(labelText: tx(context, 'note')),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text(tx(context, 'cancel')),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(
              context,
              ScoreEdit(
                  int.tryParse(points.text.trim()) ?? 0, note.text.trim()),
            ),
            child: Text(tx(context, 'save')),
          ),
        ],
      ),
    );
    points.dispose();
    note.dispose();
    return result;
  }

  Future<Map<String, dynamic>?> _userAccessDialog(
    Map<String, dynamic> user,
  ) async {
    var role = user['role']?.toString() ?? 'user';
    var school = user['school']?.toString() ?? '';
    if (school.isNotEmpty && !schools.contains(school)) {
      schools = [...schools, school];
    }
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text(user['username']?.toString() ?? tx(context, 'users')),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              DropdownButtonFormField<String>(
                value: role,
                decoration: InputDecoration(labelText: tx(context, 'role')),
                items: [
                  DropdownMenuItem(value: 'user', child: Text(tx(context, 'user_role'))),
                  DropdownMenuItem(value: 'teacher', child: Text(tx(context, 'teachers'))),
                  DropdownMenuItem(value: 'admin', child: Text(tx(context, 'admin'))),
                  const DropdownMenuItem(value: 'dev', child: Text('Dev')),
                ],
                onChanged: (value) {
                  if (value != null) setDialogState(() => role = value);
                },
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                value: school.isEmpty ? null : school,
                decoration: InputDecoration(labelText: tx(context, 'school')),
                items: [
                  for (final value in schools)
                    DropdownMenuItem(value: value, child: Text(value)),
                ],
                onChanged: (value) {
                  if (value != null) setDialogState(() => school = value);
                },
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text(tx(context, 'cancel')),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, {
                'role': role,
                'school': school,
              }),
              child: Text(tx(context, 'save')),
            ),
          ],
        ),
      ),
    );
    return result;
  }

  Future<Map<String, dynamic>?> _proVerificationDialog(
    Map<String, dynamic> user,
  ) async {
    final username = user['username']?.toString() ?? '';
    var german = user['pro_verified_german'] == true;
    var math = user['pro_verified_math'] == true;
    var english = user['pro_verified_english'] == true;
    var biology = user['pro_verified_biology'] == true;
    var pgw = user['pro_verified_pgw'] == true;
    var spanish = user['pro_verified_spanish'] == true;
    var art = user['pro_verified_art'] == true;
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text('${tx(context, 'verify_pros')}: $username'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _proVerifyTile(
                label: tx(context, 'german'),
                level: user['level_german'],
                value: german,
                onChanged: (value) => setDialogState(() => german = value),
              ),
              _proVerifyTile(
                label: tx(context, 'math'),
                level: user['level_math'],
                value: math,
                onChanged: (value) => setDialogState(() => math = value),
              ),
              _proVerifyTile(
                label: tx(context, 'english'),
                level: user['level_english'],
                value: english,
                onChanged: (value) => setDialogState(() => english = value),
              ),
              _proVerifyTile(
                label: tx(context, 'biology'),
                level: user['level_biology'],
                value: biology,
                onChanged: (value) => setDialogState(() => biology = value),
              ),
              _proVerifyTile(
                label: tx(context, 'pgw'),
                level: user['level_pgw'],
                value: pgw,
                onChanged: (value) => setDialogState(() => pgw = value),
              ),
              _proVerifyTile(
                label: tx(context, 'spanish'),
                level: user['level_spanish'],
                value: spanish,
                onChanged: (value) => setDialogState(() => spanish = value),
              ),
              _proVerifyTile(
                label: tx(context, 'art'),
                level: user['level_art'],
                value: art,
                onChanged: (value) => setDialogState(() => art = value),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text(tx(context, 'cancel')),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, {
                'german': german,
                'math': math,
                'english': english,
                'biology': biology,
                'pgw': pgw,
                'spanish': spanish,
                'art': art,
              }),
              child: Text(tx(context, 'save')),
            ),
          ],
        ),
      ),
    );
    return result;
  }

  Widget _proVerifyTile({
    required String label,
    required Object? level,
    required bool value,
    required ValueChanged<bool> onChanged,
  }) {
    final isPro = level == 'pro';
    return CheckboxListTile(
      contentPadding: EdgeInsets.zero,
      value: isPro && value,
      onChanged: isPro ? (next) => onChanged(next == true) : null,
      title: Text(label),
      subtitle: Text(isPro ? 'Pro-Level' : tx(context, 'no_pro_level')),
    );
  }

  Future<Map<String, dynamic>?> _inviteCodeDialog() async {
    var school = widget.isDev && schools.isNotEmpty
        ? schools.first
        : _defaultShopSchool();
    _ensureKnownSchool(school);
    var role = 'user';
    final roles = widget.isDev
        ? const ['user', 'teacher', 'admin', 'dev']
        : widget.adminRole == 'admin'
            ? const ['user', 'teacher']
            : const ['user'];
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text(tx(context, 'create_code')),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _schoolControl(
                school: school,
                onChanged: (value) => setDialogState(() => school = value),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                value: role,
                decoration: InputDecoration(labelText: tx(context, 'role')),
                items: [
                  for (final value in roles)
                    DropdownMenuItem(value: value, child: Text(value)),
                ],
                onChanged: (value) {
                  if (value != null) setDialogState(() => role = value);
                },
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text(tx(context, 'cancel')),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, {
                'school': school,
                'role': role,
              }),
              child: Text(tx(context, 'create')),
            ),
          ],
        ),
      ),
    );
    return result;
  }

  Future<Map<String, dynamic>?> _shopDialog(Map<String, dynamic>? item) async {
    final title = TextEditingController(text: item?['title']?.toString() ?? '');
    final description = TextEditingController(
      text: item?['description']?.toString() ?? '',
    );
    final priceHint = TextEditingController(
      text: item?['price_hint']?.toString() ?? '',
    );
    var school = item?['school']?.toString() ??
        (item == null ? _defaultShopSchool() : '');
    _ensureKnownSchool(school);
    final className = TextEditingController(
      text: widget.adminRole == 'teacher'
          ? widget.adminClass
          : (item?['class_name']?.toString() ?? ''),
    );
    final points = TextEditingController(
      text: (item?['points_price'] ?? 0).toString(),
    );
    final sort = TextEditingController(
      text: (item?['sort_order'] ?? 0).toString(),
    );
    var active = item?['active'] != false;
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title:
              Text(item == null ? tx(context, 'create_item') : tx(context, 'edit_item')),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: title,
                  decoration: InputDecoration(labelText: tx(context, 'title')),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: description,
                  maxLines: 3,
                  decoration: InputDecoration(labelText: tx(context, 'description')),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: priceHint,
                  decoration: InputDecoration(labelText: tx(context, 'price_hint')),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: points,
                  keyboardType: TextInputType.number,
                  decoration: InputDecoration(labelText: tx(context, 'points_price')),
                ),
                const SizedBox(height: 12),
                _schoolControl(
                  school: school,
                  onChanged: (value) => setDialogState(() => school = value),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: className,
                  readOnly: widget.adminRole == 'teacher',
                  decoration: InputDecoration(
                    labelText: tx(context, 'class_all'),
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: sort,
                  keyboardType: TextInputType.number,
                  decoration: InputDecoration(labelText: tx(context, 'sort_order')),
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  value: active,
                  onChanged: (value) => setDialogState(() => active = value),
                  title: Text(tx(context, 'active')),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text(tx(context, 'cancel')),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, {
                'title': title.text.trim(),
                'description': description.text.trim(),
                'price_hint': priceHint.text.trim(),
                'points_price': int.tryParse(points.text.trim()) ?? 0,
                'school': school,
                'class_name': className.text.trim(),
                'sort_order': int.tryParse(sort.text.trim()) ?? 0,
                'active': active,
              }),
              child: Text(tx(context, 'save')),
            ),
          ],
        ),
      ),
    );
    title.dispose();
    description.dispose();
    priceHint.dispose();
    className.dispose();
    points.dispose();
    sort.dispose();
    return result;
  }

  Future<Map<String, dynamic>?> _bulkShopDialog() async {
    final titles = TextEditingController();
    final priceHint = TextEditingController();
    final points = TextEditingController(text: '0');
    var school = _defaultShopSchool();
    _ensureKnownSchool(school);
    final className = TextEditingController(
      text: widget.adminRole == 'teacher' ? widget.adminClass : '',
    );
    var active = true;
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text(tx(context, 'bulk_listing')),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: titles,
                  minLines: 6,
                  maxLines: 10,
                  decoration: InputDecoration(
                    labelText: tx(context, 'items'),
                    hintText: tx(context, 'one_item_per_line'),
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: priceHint,
                  decoration: InputDecoration(labelText: tx(context, 'price_hint')),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: points,
                  keyboardType: TextInputType.number,
                  decoration: InputDecoration(labelText: tx(context, 'points_price')),
                ),
                const SizedBox(height: 12),
                _schoolControl(
                  school: school,
                  onChanged: (value) => setDialogState(() => school = value),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: className,
                  readOnly: widget.adminRole == 'teacher',
                  decoration: InputDecoration(
                    labelText: tx(context, 'class_all'),
                  ),
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  value: active,
                  onChanged: (value) => setDialogState(() => active = value),
                  title: Text(tx(context, 'active')),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text(tx(context, 'cancel')),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, {
                'titles': titles.text
                    .split(RegExp(r'\r?\n'))
                    .map((line) => line.trim())
                    .where((line) => line.isNotEmpty)
                    .toList(),
                'price_hint': priceHint.text.trim(),
                'points_price': int.tryParse(points.text.trim()) ?? 0,
                'school': school,
                'class_name': className.text.trim(),
                'active': active,
              }),
              child: Text(tx(context, 'create')),
            ),
          ],
        ),
      ),
    );
    titles.dispose();
    priceHint.dispose();
    className.dispose();
    points.dispose();
    return result;
  }

  Future<Map<String, dynamic>?> _teacherDialog(
      Map<String, dynamic>? teacher) async {
    final email =
        TextEditingController(text: teacher?['email']?.toString() ?? '');
    final name = TextEditingController(
      text: teacher?['display_name']?.toString() ?? '',
    );
    var school = teacher?['school']?.toString() ??
        (teacher == null ? _defaultShopSchool() : '');
    _ensureKnownSchool(school);
    var active = teacher?['active'] != false;
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text(
              teacher == null ? tx(context, 'create_contact') : tx(context, 'edit_contact')),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: email,
                keyboardType: TextInputType.emailAddress,
                decoration: InputDecoration(labelText: tx(context, 'email')),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: name,
                decoration: InputDecoration(labelText: tx(context, 'name')),
              ),
              const SizedBox(height: 12),
              _schoolControl(
                school: school,
                onChanged: (value) => setDialogState(() => school = value),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                value: active,
                onChanged: (value) => setDialogState(() => active = value),
                title: Text(tx(context, 'active')),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text(tx(context, 'cancel')),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, {
                'email': email.text.trim(),
                'display_name': name.text.trim(),
                'school': school,
                'active': active,
              }),
              child: Text(tx(context, 'save')),
            ),
          ],
        ),
      ),
    );
    email.dispose();
    name.dispose();
    return result;
  }
}

class ScoreEdit {
  const ScoreEdit(this.points, this.note);

  final int points;
  final String note;
}

class AdminCard extends StatelessWidget {
  const AdminCard({
    required this.title,
    required this.subtitle,
    required this.leading,
    this.trailing,
    super.key,
  });

  final String title;
  final String subtitle;
  final IconData leading;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Card(
        child: ListTile(
          leading: Icon(leading),
          title: Text(title),
          subtitle: Text(subtitle),
          trailing: trailing,
        ),
      ),
    );
  }
}

class TextEntryDialog extends StatefulWidget {
  const TextEntryDialog({
    required this.title,
    required this.label,
    required this.initialValue,
    required this.obscure,
    this.maxLength,
    super.key,
  });

  final String title;
  final String label;
  final String initialValue;
  final bool obscure;
  final int? maxLength;

  @override
  State<TextEntryDialog> createState() => _TextEntryDialogState();
}

class _TextEntryDialogState extends State<TextEntryDialog> {
  late final TextEditingController controller;

  @override
  void initState() {
    super.initState();
    controller = TextEditingController(text: widget.initialValue);
  }

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  void _submit() {
    Navigator.of(context).pop(controller.text);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.title),
      content: TextField(
        controller: controller,
        obscureText: widget.obscure,
        autofocus: true,
        maxLength: widget.maxLength,
        maxLines: widget.obscure ? 1 : null,
        decoration: InputDecoration(labelText: widget.label),
        onSubmitted: (_) => _submit(),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text(tx(context, 'cancel')),
        ),
        FilledButton(
          onPressed: _submit,
          child: Text(tx(context, 'save')),
        ),
      ],
    );
  }
}

class LevelSelector extends StatelessWidget {
  const LevelSelector({
    required this.label,
    required this.value,
    required this.onChanged,
    super.key,
  });

  final String label;
  final String value;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 6),
          SegmentedButton<String>(
            segments: [
              const ButtonSegment(value: 'pro', label: Text('Pro')),
              ButtonSegment(value: 'medium', label: Text(tx(context, 'medium'))),
              const ButtonSegment(value: 'noob', label: Text('Noob')),
            ],
            selected: {value},
            onSelectionChanged: (set) => onChanged(set.first),
          ),
        ],
      ),
    );
  }
}

class ErrorBanner extends StatelessWidget {
  const ErrorBanner(this.message, {super.key});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Text(
        message,
        style: TextStyle(color: Theme.of(context).colorScheme.error),
      ),
    );
  }
}

String levelLabel(Object? value) {
  return switch (value?.toString()) {
    'pro' => 'Pro',
    'medium' => 'Mittel',
    _ => 'Noob',
  };
}

String friendlyError(BuildContext context, Object ex) {
  if (ex is ApiException) {
    if (ex.message != null && ex.message!.isNotEmpty) return ex.message!;
    return switch (ex.code) {
      'shortpass' => tx(context, 'password_short'),
      'shortuser' => tx(context, 'username_short'),
      'pwd_incomplete' => tx(context, 'all_password_fields'),
      'pwd_current_wrong' => tx(context, 'current_password_wrong'),
      'ban_message_required' => tx(context, 'ban_reason_required'),
      'ban_message_too_long' => tx(context, 'ban_reason_too_long'),
      'mismatch' => tx(context, 'password_mismatch'),
      'taken' => tx(context, 'username_taken'),
      'invalid' => tx(context, 'login_invalid'),
      'bad_invite' => tx(context, 'bad_invite'),
      'bad_contact_email' => tx(context, 'bad_contact_email'),
      'bad_iserv_email' => tx(context, 'bad_iserv_email'),
      'notify_no_email' => tx(context, 'notify_no_email'),
      'invalid_avatar_url' => tx(context, 'invalid_avatar_url'),
      'invalid_school' => tx(context, 'invalid_school'),
      'invalid_logo_url' => tx(context, 'invalid_logo_url'),
      'invalid_role' => tx(context, 'invalid_role'),
      'invalid_limit' => tx(context, 'invalid_limit'),
      'code_limit' => tx(context, 'code_limit'),
      'invalid_datetime' => tx(context, 'invalid_datetime'),
      'empty_location' => tx(context, 'empty_location'),
      'invalid_location' => tx(context, 'invalid_location'),
      'permission' => tx(context, 'permission'),
      'no_appointment' => tx(context, 'no_appointment_error'),
      'not_started' => tx(context, 'not_started'),
      'already_ended' => tx(context, 'already_ended'),
      'appointment_ended' => tx(context, 'chat_ended_local'),
      'room_closed' => tx(context, 'room_closed_error'),
      'already_reported' => tx(context, 'already_reported'),
      'message_not_found' => tx(context, 'message_not_found'),
      'own_message' => tx(context, 'own_message'),
      'reason_too_long' => tx(context, 'reason_too_long'),
      'report_not_found' => tx(context, 'report_not_found'),
      'not_ended' => tx(context, 'not_ended'),
      'need_comment' => tx(context, 'need_comment_local'),
      'not_in_room' => tx(context, 'not_in_room'),
      'setup_done' => tx(context, 'setup_done'),
      'auth' => tx(context, 'auth'),
      'forbidden' => tx(context, 'forbidden'),
      _ => ex.code,
    };
  }
  return ex.toString();
}
