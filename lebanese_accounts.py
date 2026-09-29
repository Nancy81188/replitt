"""Lebanese Standard Chart of Accounts (PCGL).

Data adapted from the open-source erpnext_lebanese localization, which identifies
its chart as based on Lebanese Ministry of Finance Decision 111/1 (22-02-1982).
Each row: code, English name, Arabic name, French name, internal type, parent code.
"""

LEBANESE_ACCOUNTS = [
  [
    "1",
    "Equity & Long Term Debts",
    "رأس المال",
    "Comptes de Capitaux Permanents",
    "equity",
    None
  ],
  [
    "10",
    "Capital",
    "رأس المال",
    "Capital",
    "equity",
    "1"
  ],
  [
    "101",
    "Capital (Company or Individual)",
    " (للشركة أو للشخص) رأس المال",
    "Capital Social ou Personnel",
    "equity",
    "10"
  ],
  [
    "1011",
    "Subscribed Un-Called Capital",
    "رأس المال المكتتب وغيرالمستدعى",
    "Capital Souscrit, Non Appelé",
    "equity",
    "101"
  ],
  [
    "1012",
    "Subscribed Called & Unpaid Capital",
    "رأس المال المكتتب، المستدعى وغيرالمدفوع",
    "Capital Souscrit, Appelé, Non Versé",
    "equity",
    "101"
  ],
  [
    "1013",
    "Subscribed Called & Paid-Up Capital",
    "رأس المال المكتتب، المستدعى والمدفوع",
    "Capital Souscrit, Appelé, Versé",
    "equity",
    "101"
  ],
  [
    "102",
    "Capital Premiums",
    "علاوات الإصدار والإندماج والمقدّمات",
    "Primes Liées au Capital Social",
    "equity",
    "10"
  ],
  [
    "1021",
    "Issuance Premiums",
    "علاوات الإصدار",
    "Primes d’Émission",
    "equity",
    "102"
  ],
  [
    "1022",
    "Merger Premiums",
    "علاوات الإندماج",
    "Primes de Fusion",
    "equity",
    "102"
  ],
  [
    "1023",
    "Contributions Premiums",
    "علاوات المقدّمات",
    "Primes d’Apport",
    "equity",
    "102"
  ],
  [
    "1024",
    "Conversion Premiums of Bonds to Shares",
    "علاوات تحويل السندات إلى أسهم",
    "Primes de Conversion d’Obligations en Actions",
    "equity",
    "102"
  ],
  [
    "103",
    "Revaluation Variances",
    "فروقات إعادة التخمين",
    "Ecarts de Réévaluation",
    "equity",
    "10"
  ],
  [
    "1031",
    "Non-Amortizable Assets Revaluation Variances",
    "فروقات إعادة تخمين أصول غير قابلة للإستهلاك",
    "Écarts de Réévaluation – Immobilisations Non Amortissables",
    "equity",
    "103"
  ],
  [
    "1035",
    "Amortizable Assets Revaluation Variances",
    "فروقات إعادة تخمين أصول قابلة للإستهلاك",
    "Écarts de Réévaluation – Immobilisations Amortissables",
    "equity",
    "103"
  ],
  [
    "109",
    "Owner’s Current Account",
    "الحساب الشخصي لصاحب المؤسّسة",
    "Compte de l’Exploitant Individuel",
    "equity",
    "10"
  ],
  [
    "11",
    "Reserves",
    "الإحتياطات",
    "Réserves",
    "equity",
    "1"
  ],
  [
    "111",
    "Legal Reserves",
    "إحتياطي قانوني",
    "Réserve Légale",
    "equity",
    "11"
  ],
  [
    "112",
    "Statutory & Contractual Reserves",
    "إحتياطيات نظامية وتعاقدية",
    "Réserves Statutaires ou Contractuelles",
    "equity",
    "11"
  ],
  [
    "119",
    "Other Reserves",
    "إحتياطيات أخرى",
    "Autres Réserves",
    "equity",
    "11"
  ],
  [
    "12",
    "Brought Forward Results",
    "نتائج سابقة مدورة",
    "Report à Nouveau",
    "equity",
    "1"
  ],
  [
    "121",
    "Brought Forward Results - Profits",
    "نتائج سابقة دائنة مدوّرة - أرباح",
    "Report à Nouveau Crédit – Profits",
    "equity",
    "12"
  ],
  [
    "125",
    "Brought Forward Results - Losses",
    "نتائج سابقة مدينة مدوّرة - خسائر",
    "Report à Nouveau Débit – Pertes",
    "equity",
    "12"
  ],
  [
    "13",
    "Current Year Net Results",
    "النتيجة الصافية للدورة المالية",
    "Résultat Net de l’Exercice",
    "equity",
    "1"
  ],
  [
    "131",
    "Gross Trade Margin",
    "الهامش التجارى القائم",
    "Marge Commerciale Brute",
    "equity",
    "13"
  ],
  [
    "132",
    "Value Added",
    "القيمة المضافة",
    "Valeur Ajoutée",
    "equity",
    "13"
  ],
  [
    "133",
    "Gross Trading Operating Margin",
    "الفائض غير الصافي للاستثمار",
    "Excédent Brut d’Exploitation",
    "equity",
    "13"
  ],
  [
    "134",
    "Operating Result Before Financial Income and Expenses",
    "النتيجة الجارية قبل الضريبة",
    "Résultat d’Exploitation Avant Impôt",
    "equity",
    "13"
  ],
  [
    "135",
    "Result Before Taxation",
    "نتيجة الدورة المالية - أرباح",
    "Résultat de l’Exercice Avant Impôt",
    "equity",
    "13"
  ],
  [
    "136",
    "Non Operating Result",
    "النتيجة خارج الاستثمار",
    "Résultat Hors Exploitation",
    "equity",
    "13"
  ],
  [
    "138",
    "Current Year Results - Profits",
    "نتيجة الدورة المالية - أرباح",
    "Résultat de l’Exercice – Bénéfice",
    "equity",
    "13"
  ],
  [
    "139",
    "Current Year Results - Losses",
    "نتيجة الدورة المالية - خسائر",
    "Résultat de l’Exercice – Perte",
    "equity",
    "13"
  ],
  [
    "14",
    "Investment Subsidies",
    "إعانات للتوظيفات",
    "Subvention d’Investissement",
    "equity",
    "1"
  ],
  [
    "141",
    "Investment Subsidies Received",
    "إعانات للتوظيفات مقبوضة",
    "Subventions d’Investissement Reçues",
    "equity",
    "14"
  ],
  [
    "145",
    "Investment Subsidies Transferred To Results",
    "إعانات للتوظيفات محوّلة للنتائج",
    "Subventions d’Investissement Rapportées aux Résultats",
    "equity",
    "14"
  ],
  [
    "15",
    "Provisions For Contingencies & Charges",
    "مؤونات لمواجهة أخطار وأعباء",
    "Provisions pour Risques et Charges",
    "equity",
    "1"
  ],
  [
    "151",
    "Provisions For Risks",
    "مؤونات لمواجهة أخطار",
    "Provisions pour Risques",
    "equity",
    "15"
  ],
  [
    "1511",
    "Provisions for Litigations & Alike",
    "مؤونات أخطار المنازعات والإحتمالات",
    "Provisions pour Litiges et Éventualités Diverses",
    "equity",
    "151"
  ],
  [
    "1512",
    "Provisions against Guarantees Given",
    "مؤونات لقاء الضمانات المعطات للزبائن",
    "Provisions pour Garanties Données aux Clients",
    "equity",
    "151"
  ],
  [
    "1513",
    "Provisions for Losses on Exchange",
    "مؤونات مواجهة خسائر سعر الصرف",
    "Provisions pour Pertes de Change",
    "equity",
    "151"
  ],
  [
    "1514",
    "Provisions for Losses on Forward Contracts",
    "مؤونات مواجهة خسائر على عقود لأجل",
    "Provisions pour Pertes sur Marchés à Terme",
    "equity",
    "151"
  ],
  [
    "1515",
    "Provisions for Fines & Penalties",
    "مؤونات مواجهة الغرامات والجزاءات",
    "Provisions pour Amendes et Pénalités",
    "equity",
    "151"
  ],
  [
    "1516",
    "Provisions for Financial Risks",
    "مؤونات مواجهة المخاطر والأعباء المالية",
    "Provisions pour Risques Financiers",
    "equity",
    "151"
  ],
  [
    "1517",
    "Provisions for Extraordinary Prices Fall",
    "مؤونات مواجهة هبوط أسعار إستثنائي",
    "Provisions pour Chutes des Prix Extraordinaires",
    "equity",
    "151"
  ],
  [
    "1518",
    "Provisions for Non-Operational Risks & Charges",
    "مؤونات مواجهة أخطار وأعباء خارج الإستثمار",
    "Provisions pour Risques et Charges Hors Exploitation",
    "equity",
    "151"
  ],
  [
    "155",
    "Provisions For Charges",
    "مؤونات لمواجهة أعباء",
    "Provisions pour Charges",
    "equity",
    "15"
  ],
  [
    "1551",
    "Provisions for Deferred Charges",
    "مؤونات الأعباء الواجب توزيعها على عدة دورات",
    "Provisions pour Charges à Répartir sur Plusieurs Exercices",
    "equity",
    "155"
  ],
  [
    "1552",
    "Provisions for Employee End-of-Service and Similar Obligations",
    "مؤونات لمواجهة معاشات التقاعد وموجبات مماثلة",
    "Provisions pour Indemnités de Fin de Service et Obligations Assimilées",
    "equity",
    "155"
  ],
  [
    "1552.1",
    "Provisions for End of Service Indemnity",
    "مؤونات تسوية تعويضات نهاية الخدمة",
    "Provisions pour Indemnités de Fin de Service",
    "equity",
    "1552"
  ],
  [
    "1552.2",
    "Provisions for End of Service Pensions",
    "مؤونات دفع معاشات التقاعد",
    "Provisions pour Pensions de Retraite",
    "equity",
    "1552"
  ],
  [
    "1552.3",
    "Provisions for Workmen’s Compensations",
    "مؤونات لتعويضات طوارئ العمل",
    "Provisions pour Accidents de Travail",
    "equity",
    "1552"
  ],
  [
    "1553",
    "Provision for Taxes (Other than Income Tax)",
    "مؤونات للضرائب (غير ضريبة الأرباح)",
    "Provisions pour Impôts (non sur le Revenu)",
    "equity",
    "1552"
  ],
  [
    "16",
    "Long & Medium Term Debts",
    "ديون مالية طويلة ومتوسطة الأجل",
    "Dettes Financières à Long et Moyen Terme",
    "equity",
    "15"
  ],
  [
    "161",
    "Loans Against Debentures",
    "قروض لأجل لقاء سندات دين",
    "Emprunts Obligataires",
    "equity",
    "16"
  ],
  [
    "162",
    "Long Term Loans From Financial Institutions",
    "قروض لأجل من المصارف ومؤسّسات التسليف",
    "Emprunts auprès d’Établissements de Crédit",
    "equity",
    "16"
  ],
  [
    "168",
    "Sundry Long & Medium Term Loans",
    "قروض وديون متفرّقة لأجل",
    "Emprunts et Dettes Divers",
    "equity",
    "16"
  ],
  [
    "1681",
    "Notes Payable Resulting from the Purchase of the Business",
    "أوراق دفع ناجمة عن شراء المؤسسة التجارية",
    "Effets à Payer Résultant de l’Acquisition du Fonds de Commerce",
    "equity",
    "168"
  ],
  [
    "1682",
    "Deposits and Guarantees Received",
    "ودائع و كفالات",
    "Dépôts et Garanties Reçus",
    "equity",
    "168"
  ],
  [
    "1683",
    "Advances from the Government",
    "سلفات الدولة",
    "Avances de l’État",
    "equity",
    "168"
  ],
  [
    "1684",
    "Capitalized Life Annuities",
    "دخل لمدى الحياة متراكم",
    "Rentes Viagères Capitalisées",
    "equity",
    "168"
  ],
  [
    "1689",
    "Other Medium and Long Term Debts",
    "ديون أخرى طويلة ومتوسطة الأجل",
    "Autres Dettes à Moyen et Long Terme",
    "equity",
    "168"
  ],
  [
    "18",
    "Accounts with Affiliated Companies and Branches",
    "حسابات إرتباط المؤسّسات والفروع",
    "Comptes de Liaison des Établissements, Succursales",
    "equity",
    "16"
  ],
  [
    "181",
    "Branches and Joint Ventures Accounts",
    "حسابات ارتباط المؤسسات والفروع وشركات المشاركة (حساب مستقل لكل مؤسسة)",
    "Comptes de Liaison des Succursales et Entreprises en Participation",
    "equity",
    "18"
  ],
  [
    "1811",
    "Balance Brought Forward",
    "رصيد مدور",
    "Solde Reporté",
    "equity",
    "181"
  ],
  [
    "1815",
    "Movements of the Period",
    "حركات الدورة المالية",
    "Mouvements de la Période",
    "equity",
    "181"
  ],
  [
    "186",
    "Intercompany Charges",
    "أعباء ناتجة عن معاملات متبادلة بين المؤسسات والفروع",
    "Charges Inter-entreprises",
    "equity",
    "181"
  ],
  [
    "187",
    "Intercompany Income",
    "إيرادات ناتجة عن معاملات متبادلة بين المؤسسات والفروع",
    "Produits Inter-entreprises",
    "equity",
    "181"
  ],
  [
    "19",
    "Accounts for the Aggregation of Charges and Income",
    "حسابات تجميع الأعباء والإيرادات",
    "Comptes de Regroupement des Charges et des Produits",
    "equity",
    "16"
  ],
  [
    "191",
    "Determination of Gross Trading Margin",
    "تحديد الهامش التجاري القائم",
    "Détermination de la Marge Commerciale Brute",
    "equity",
    "19"
  ],
  [
    "192",
    "Determination of Value Added",
    "تحديد القيمة المضافة",
    "Détermination de la Valeur Ajoutée",
    "equity",
    "19"
  ],
  [
    "193",
    "Determination of Gross Operating Surplus",
    "تحديد الفائض غير الصافي للاستثمار",
    "Détermination de l’Excédent Brut d’Exploitation",
    "equity",
    "19"
  ],
  [
    "194",
    "Determination of Operating Result Before Financial Income and Expenses",
    "تحديد نتيجة الاستثمار قبل الإيرادات والمصاريف المالية",
    "Détermination du Résultat d’Exploitation Avant Produits et Charges Financiers",
    "equity",
    "19"
  ],
  [
    "195",
    "Determination of Current Result Before Taxation",
    "تحديد النتيجة الجارية قبل الضريبة",
    "Détermination du Résultat Courant Avant Impôt",
    "equity",
    "19"
  ],
  [
    "196",
    "Determination of Non-Operating Result",
    "تحديد النتيجة خارج الاستثمار",
    "Détermination du Résultat Hors Exploitation",
    "equity",
    "19"
  ],
  [
    "197",
    "Determination of the Period Result",
    "تحديد نتيجة الدورة المالية",
    "Détermination du Résultat de l’Exercice",
    "equity",
    "19"
  ],
  [
    "2",
    "Fixed Assets",
    "حسابات الأصول الثابتة",
    "Comptes d’Immobilisations",
    "asset",
    None
  ],
  [
    "21",
    "Intangible Fixed Assets",
    "الاصول الثابتة غير المادية",
    "Immobilisations Incorporelles",
    "asset",
    "2"
  ],
  [
    "211",
    "Business Concern",
    "المؤسّسة التجارية - (الخلو، الشهرة، الزبائن..)",
    "Fonds de Commerce",
    "asset",
    "21"
  ],
  [
    "212",
    "Formation Expenses",
    "مصاريف التأسيس",
    "Frais d’Établissement",
    "asset",
    "21"
  ],
  [
    "213",
    "Research & Development Expenses",
    "مصاريف البحوث والتطوير",
    "Frais de Recherche et de Développement",
    "asset",
    "21"
  ],
  [
    "214",
    "Patents, License, Trade Marks & Alike",
    "براءات الإختراع، الإجازات، العلامات، وخلافها",
    "Brevets, Licences, Marques et Valeurs Similaires",
    "asset",
    "21"
  ],
  [
    "219",
    "Other Intangible Fixed Assets",
    "أصول ثابتة غير مادية أخرى",
    "Autres Immobilisations Incorporelles",
    "asset",
    "21"
  ],
  [
    "2191",
    "Miscellaneous Intangible Fixed Assets",
    "أصول ثابتة غير مادية متنوعة",
    "Autres Immobilisations Diverses",
    "asset",
    "21"
  ],
  [
    "2198",
    "Advance Payments on Account of Intangible Fixed Assets",
    "سلف ودفعات على حساب اقتناء أصول ثابتة غير مادية",
    "Avances et Acomptes sur Immobilisations Incorporelles",
    "asset",
    "21"
  ],
  [
    "22",
    "Tangible Fixed Assets",
    "الاصول الثابتة المادية",
    "Immobilisations Corporelles",
    "asset",
    "2"
  ],
  [
    "221",
    "Lands",
    "الأراضي",
    "Terrains",
    "asset",
    "22"
  ],
  [
    "2211",
    "Virgin Lands - Basic Cost",
    "الأراضي الفراغ - القيمة الأساسية",
    "Terrains Nus",
    "asset",
    "221"
  ],
  [
    "2212",
    "Built-on Properties - Basic Cost",
    "الأراضي المبنية - القيمة الأساسية",
    "Terrains Bâtis (Ensembles Immobiliers)",
    "asset",
    "221"
  ],
  [
    "2213",
    "Extractive Lands - Basic Cost",
    "أراضي الإستثمار الجوفي - القيمة الأساسية",
    "Terrains d’Exploitation (Carrières, Gisements)",
    "asset",
    "221"
  ],
  [
    "2214",
    "Land Improvements and Reclamation",
    "تكاليف إستصلاح وتنظيم الأراضي",
    "Agencements et Aménagements de Terrains",
    "asset",
    "221"
  ],
  [
    "223",
    "Buildings & Constructions",
    "الأبنية والمنشآت وتجهيزاتها",
    "Constructions et Bâtiments",
    "asset",
    "22"
  ],
  [
    "2231",
    "Buildings - Basic Cost",
    "الأبنية - القيمة الأساسية",
    "Bâtiments (Ensembles Immobiliers)",
    "asset",
    "223"
  ],
  [
    "2232",
    "Installations & Leasehold Improvements",
    "التجهيزات العامة وإستصلاح الأبنية",
    "Installations Générales, Agencements et Aménagements des Constructions",
    "asset",
    "223"
  ],
  [
    "2233",
    "Infra-structure Constructions",
    "إنشاءات البنى التحتية",
    "Ouvrages d’Infrastructures",
    "asset",
    "223"
  ],
  [
    "2234",
    "Constructions on Other Owners’ Lands",
    "إنشاءات على أراضي الغير",
    "Constructions sur Terrains d’Autrui",
    "asset",
    "223"
  ],
  [
    "224",
    "Technical Installations, Machinery & Equipment",
    "التجهيزات الفنية والآلات الصناعية",
    "Installations Techniques, Matériels et Outils Industriels",
    "asset",
    "22"
  ],
  [
    "2241",
    "Specialized Technical Installations",
    "تجهيزات متخصّصة",
    "Installations Complexes Spécialisées",
    "asset",
    "224"
  ],
  [
    "2242",
    "Specific Technical Installations",
    "تجهيزات ذات طبيعة خاصة",
    "Installations à Caractère Spécifique",
    "asset",
    "224"
  ],
  [
    "2243",
    "Industrial Machinery & Equipment",
    "الآلات والمعدّات الصناعية",
    "Matériels Industriels",
    "asset",
    "224"
  ],
  [
    "2244",
    "Industrial Tools",
    "الأدوات الصناعية",
    "Outillages Industriels",
    "asset",
    "224"
  ],
  [
    "225",
    "Transportation Equipment",
    "المركبات وآليات النقل",
    "Matériel de transport",
    "asset",
    "22"
  ],
  [
    "2251",
    "Passenger Vehicles",
    "سيارات سياحية",
    "Voitures de Passagers",
    "asset",
    "225"
  ],
  [
    "2252",
    "Transport Vehicles & Handling Equipment",
    "شاحنات وآليات نقل",
    "Véhicules et Matériel de Transport",
    "asset",
    "225"
  ],
  [
    "226",
    "Other Tangible Fixed Assets",
    "أصول ثابتة مادية أخرى",
    "Autres Immobilisations Corporelles",
    "asset",
    "22"
  ],
  [
    "2261",
    "General installations & Improvements",
    "تجهيزات عامة وتحسينات مختلفة",
    "Installations Générales, Agencements, Aménagements Divers",
    "asset",
    "226"
  ],
  [
    "2262",
    "Office & Computer Equipment",
    "ادوات مكتبية ومعلوماتية",
    "Matériel de Bureau et Informatique",
    "asset",
    "226"
  ],
  [
    "2262.1",
    "Office Equipment",
    "ادوات مكتبية",
    "Matériel de Bureau",
    "asset",
    "2262"
  ],
  [
    "2262.2",
    "Computer Equipment",
    "ادوات معلوماتية",
    "Matériel Informatique",
    "asset",
    "2262"
  ],
  [
    "2263",
    "Furnitures & Fixtures",
    "أثاث ومفروشات",
    "Mobilier",
    "asset",
    "226"
  ],
  [
    "2264",
    "Agricultural Installations",
    "إستثمارات زراعية",
    "Cheptel – Installations Agricoles",
    "asset",
    "226"
  ],
  [
    "2265",
    "Re-usable Containers",
    "عبوات قابلة لإعادة الإستعمال",
    "Emballages Réutilisables",
    "asset",
    "226"
  ],
  [
    "2265.1",
    "Re-usable Containers - Barils, Bottles & Boxes",
    "عبوات قابلة لإعادة الإستعمال - البراميل والقناني والصناديق العر",
    "Emballages Réutilisables - Barils, Bouteilles et Caisses",
    "asset",
    "2265"
  ],
  [
    "2265.2",
    "Re-usable Containers - Gaz Containers",
    "عبوات قابلة لإعادة الإستعمال - قوارير الغاز",
    "Emballages Réutilisables - Bonbonnes de Gaz",
    "asset",
    "2265"
  ],
  [
    "227",
    "Tangible Fixed Assets In Progress",
    "اصول ثابتة مادية قيد الصنع",
    "Immobilisations Corporelles en Cours",
    "asset",
    "22"
  ],
  [
    "2271",
    "Lands under Acquisition",
    "أراض قيد الإمتلاك",
    "Terrains en Cours d’Acquisition",
    "asset",
    "227"
  ],
  [
    "2273",
    "Buildings under Construction",
    "أبنية قيد الإنشاء",
    "Constructions en Cours",
    "asset",
    "227"
  ],
  [
    "2274",
    "Industrial Equipment under Installation",
    "تجهيزات ومعدّات صناعية قيد التركيب",
    "Installations Techniques, Matériels et Outillages en Cours",
    "asset",
    "227"
  ],
  [
    "2276",
    "Other Tangible Fixed Assets in Progress",
    "أصول ثابتة مادية أخرى قيد الإنجاز",
    "Autres Immobilisations Corporelles en Cours",
    "asset",
    "227"
  ],
  [
    "228",
    "Advances and Down Payments on Fixed Assets",
    "سلفات ودفعات على حساب شراء أصول ثابتة مادية",
    "Avances et Acomptes sur Immobilisations Corporelles",
    "asset",
    "22"
  ],
  [
    "25",
    "Financial Fixed Assets",
    "الاصول الثابتة المالية",
    "Immobilisations Financières",
    "asset",
    "2"
  ],
  [
    "251",
    "Equity Participations",
    "سندات مشاركة",
    "Titres de Participation",
    "asset",
    "25"
  ],
  [
    "252",
    "Receivables Related To Participations",
    "ذمم مدينة مرتبطة بمشاركات",
    "Créances Rattachées à des Participations",
    "asset",
    "25"
  ],
  [
    "253",
    "Other Securities & Financial Assets",
    "سندات أخرى مجمّدة",
    "Autres Titres Immobilisés",
    "asset",
    "25"
  ],
  [
    "2531",
    "Equity Securities (Shares and Partnership Interests)",
    "سندات ملكية (أسهم، حصص شراكة)",
    "Droit de Propriété (Actions, Parts Sociales)",
    "asset",
    "253"
  ],
  [
    "2535",
    "Debt Securities (Bonds and Notes)",
    "سندات ديـن (سندات، قسائم)",
    "Droit de Créance (Obligations, Bons)",
    "asset",
    "253"
  ],
  [
    "255",
    "Long & Medium Term Loans",
    "قروض طويلة ومتوسّطة الأجل",
    "Prêts à Long et Moyen Terme",
    "asset",
    "25"
  ],
  [
    "2551",
    "Long and Medium-Term Loans to Partners and Affiliates",
    "قروض آجلة للشركاء",
    "Prêts à Long et Moyen Terme aux Associés",
    "asset",
    "255"
  ],
  [
    "2552",
    "Long and Medium-Term Loans to Employees",
    "قروض آجلة للمستخدمين",
    "Prêts à Long et Moyen Terme au Personnel",
    "asset",
    "255"
  ],
  [
    "2558",
    "Other Long & Medium Term Loans",
    "قروض أخرى طويلة أو متوسّطة الأجل",
    "Autres Prêts à Long et Moyen Terme",
    "asset",
    "255"
  ],
  [
    "259",
    "Other Long & Medium Term Receivables",
    "ذمم مدينة أخرى مجمّدة",
    "Autres Créances à Long et Moyen Terme",
    "asset",
    "25"
  ],
  [
    "27",
    "Fixed Assets Non-Amortizable Revaluation Variation",
    "فروقات إعادة تخمين أصول غير قابلة للإستهلاك",
    "Écart de Réévaluation Immobilisations Non Amortissables",
    "asset",
    "2"
  ],
  [
    "2701",
    "Intangible Fixed Assets Non-Amortizable Revaluation Variation",
    "فروقات إعادة تخمين أصول غير مادية غير قابلة للإستهلاك",
    "Écart de Réévaluation Non Amortissable des Immobilisations Incorporelles",
    "asset",
    "27"
  ],
  [
    "2702",
    "Tangible Fixed Assets Non-Amortizable Revaluation Variation",
    "فروقات إعادة تخمين أصول مادية غير قابلة للإستهلاك",
    "Écart de Réévaluation Non Amortissable des Immobilisations Corporelles",
    "asset",
    "27"
  ],
  [
    "2705",
    "Financial Fixed Assets Non-Amortizable Revaluation Variation",
    "فروقات إعادة تخمين أصول مالية غير قابلة للإستهلاك",
    "Écart de Réévaluation Non Amortissable des Immobilisations Financières",
    "asset",
    "27"
  ],
  [
    "28",
    "Depreciation of Fixed Assets",
    "استهلاكات الاصول الثابتة",
    "Amortissements des Immobilisations",
    "asset",
    "2"
  ],
  [
    "280",
    "Amortization of Business Concern",
    "إستهلاك المؤسّسة التجارية",
    "Amortissement du Fonds de Commerce",
    "asset",
    "28"
  ],
  [
    "281",
    "Amortization of Other Intangible Fixed Assets",
    "إستهلاكات الأصول الثابتة غير المادية الأخرى",
    "Amortissement des Autres Immobilisations Incorporelles",
    "asset",
    "28"
  ],
  [
    "2811",
    "Amortization of Establishment Expenses",
    "إستهلاك مصاريف التأسيس",
    "Amortissement des Frais d’Établissement",
    "asset",
    "281"
  ],
  [
    "2812",
    "Amortization of Research & Development Expenses",
    "إستهلاك مصاريف البحوث والتطوير",
    "Amortissement des Frais de Recherche et de Développement",
    "asset",
    "281"
  ],
  [
    "2813",
    "Amortization of Patents, Licenses, Trade Marks, etc..",
    "إستهلاك براءات الإختراع والإجازات وخلافها",
    "Amortissement des Brevets, Licences et Autres",
    "asset",
    "281"
  ],
  [
    "2819",
    "Amortization of Miscellaneous Other Intangible Fixed Assets",
    "إستهلاك أصول ثابتة غير مادية أخرى",
    "Amortissement des Immobilisations Incorporelles Diverses",
    "asset",
    "281"
  ],
  [
    "282",
    "Depreciation of Tangible Fixed Assets",
    "استهلاكات الاصول الثابتة المادية",
    "Amortissements des Immobilisations Incorporelles",
    "asset",
    "28"
  ],
  [
    "2821",
    "Depreciation of Extractive Lands & Landscaping",
    "إستهلاك الأراضي - إستثمار جوفي وإستصلاح",
    "Amortissement des Terrains d’Exploitation et de Réaménagement",
    "asset",
    "282"
  ],
  [
    "2823",
    "Depreciation of Buildings & Constructions",
    "إستهلاك الأبنية وتجهيزاتها",
    "Amortissement des Constructions",
    "asset",
    "282"
  ],
  [
    "2823.11",
    "Depreciation Concrete Buildings for Trade, Tourism and Services",
    "إستهلاك الأبنيةالمشادة بالباطون والمستعملة لغاية تجارية وسياحية وخدماتية",
    "Amortissement Batis Beton pour Commerce, Tourisme et Service",
    "asset",
    "2823"
  ],
  [
    "2823.12",
    "Depreciation Concrete Buildings for Industry",
    "إستهلاك الأبنيةالمشادة بالباطون والمستعملة لغاية حرفية وصناعية",
    "Amortissement Batis Beton pour Manufactures et Industries",
    "asset",
    "2823"
  ],
  [
    "2823.13",
    "Depreciation Metallic Buildings for Trade or Industry",
    "إستهلاك أبنية وانشاءات معدنية لغاية تجارية او صناعية",
    "Amortissement Batis Metalliques pour Commerce et Industries",
    "asset",
    "2823"
  ],
  [
    "2823.21",
    "Depreciation Building Installations & Improvements",
    "إستهلاك تجهيزات الأبنية واستصلاحها",
    "Amortissement Installations et Amenagement des Contructions",
    "asset",
    "2823"
  ],
  [
    "2823.3",
    "Depreciation Infrastructures",
    "إستهلاك انشاءات البنى التحتية",
    "Amortissement des Infrastructures",
    "asset",
    "2823"
  ],
  [
    "2823.4",
    "Depreciation Constructions on Unowned Lands",
    "إستهلاك انشاءات على أراضي الغير",
    "Amortissement Constructions sur Terrains d'Autrul",
    "asset",
    "2823"
  ],
  [
    "2824",
    "Depreciation of Machinery & Equipment",
    "إستهلاك التجهيزات الفنية والآلات الصناعية",
    "Amortissement des Installations Techniques, Matériels et Outillages Industriels",
    "asset",
    "282"
  ],
  [
    "2824.1",
    "Depreciation Specialized Technical Installations",
    "إستهلاك تجهيزات الفنية متخصصة",
    "Amortissement Installations Techniques Complexes Specialisees",
    "asset",
    "2824"
  ],
  [
    "2824.2",
    "Depreciation Specific Technical Installations",
    "إستهلاك تجهيزات الفنية ذات طبيعة خاصة",
    "Amortissement Installations a Caractero Specifique",
    "asset",
    "2824"
  ],
  [
    "2824.3",
    "Depreciation Industrial Machinery & Equipment",
    "إستهلاك الألات والمعدات الصناعية",
    "Amortissement Materiels Industriels",
    "asset",
    "2824"
  ],
  [
    "2824.4",
    "Depreciation Industrial Tools",
    "إستهلاك الأدوات الصناعية",
    "Amortissement Outillages Industriels",
    "asset",
    "2824"
  ],
  [
    "2824.5",
    "Depreciation Hotels & Restaurants Appliances",
    "إستهلاك الأواني الزجاجية والأدوات الفضية في الفنادق والمطاعم",
    "Amortissement Articles & Equipements pour Hotels et Restaraunts",
    "asset",
    "2824"
  ],
  [
    "2825",
    "Depreciation of Passenger & Transport Vehicles",
    "إستهلاك المركبات وآليات النقل",
    "Amortissement des Véhicules et du Matériel de Transport",
    "asset",
    "282"
  ],
  [
    "2825.1",
    "Depreciation Passenger Vehicles",
    "إستهلاك سيارات سياحية",
    "Amortissement Voitures de Passagers",
    "asset",
    "2825"
  ],
  [
    "2826",
    "Depreciation of Other Tangible Fixed Assets",
    "إستهلاك الأصول الثابتة المادية الأخرى",
    "Amortissement d’Autres Immobilisations Corporelles",
    "asset",
    "282"
  ],
  [
    "29",
    "Provisions for Impairment of Fixed Assets",
    "مؤنات تدنّي قيم الاصول الثابتة",
    "Provisions pour Dépréciation d’Immobilisations",
    "asset",
    "2"
  ],
  [
    "290",
    "Provisions for Impairment of Business Concern",
    "مؤونة تدنّي قيمة المؤسّسة التجارية",
    "Provisions pour Dépréciation du Fonds de Commerce",
    "asset",
    "29"
  ],
  [
    "291",
    "Provisions for Impairment of Intangible Fixed Assets",
    "مؤونة هبوط قيم الأصول الثابتة غير المادية",
    "Provisions pour Dépréciation des Immobilisations Incorporelles",
    "asset",
    "29"
  ],
  [
    "2911",
    "Provisions for Impairment of Patents, Trade Marks & Alike",
    "مؤونة تدنّي قيمة براءات وإجازات وعلامات",
    "Provisions pour Dépréciation des Marques et Valeurs Similaires",
    "asset",
    "291"
  ],
  [
    "2919",
    "Provisions for Impairment of Other Intangible Fixed Assets",
    "مؤونة تدنّي قيمة أصول غير مادية أخرى",
    "Provisions pour Dépréciation d’Autres Immobilisations Incorporelles",
    "asset",
    "291"
  ],
  [
    "292",
    "Provisions for Devaluation of tangible fixed assets",
    "مؤنات تدنّي قيم الاصول الثابتة المادية",
    "Provisions pour Dépréciation des Immobilisations Corporelles",
    "asset",
    "29"
  ],
  [
    "2921",
    "Virgin Land Devaluation Provision",
    "مؤونة تدنّي قيمة الأراضي الفراغ",
    "Provisions pour Dépréciation des Terrains Nus",
    "asset",
    "292"
  ],
  [
    "2923",
    "Buildings Devaluation Provision",
    "مؤونة تدنّي قيمة الأبنية",
    "Provisions pour Dépréciation des Bâtiments",
    "asset",
    "292"
  ],
  [
    "2926",
    "Devaluation Provisions for Other Tangible Fixed Assets",
    "مؤونة تدنّي أصول ثابتة مادية أخرى",
    "Provisions pour Dépréciation d’Autres Immobilisations Corporelles",
    "asset",
    "292"
  ],
  [
    "295",
    "Provision for Devaluation of Financial Fixed Assets",
    "مؤونات تدنّي قيم الأصول المالية",
    "Provisions pour Dépréciation des Immobilisations Financières",
    "asset",
    "29"
  ],
  [
    "2951",
    "Devaluation Provisions for Equity Participations",
    "مؤونة تدنّي سندات مشاركة",
    "Provisions pour Dépréciation des Titres de Participation",
    "asset",
    "295"
  ],
  [
    "2952",
    "Devaluation Provisions for Participations’ Receivables",
    "مؤونة تدنّي ذمم مدينة مرتبطة بمشاركات",
    "Provisions pour Dépréciation des Créances Rattachées à des Participations",
    "asset",
    "295"
  ],
  [
    "2953",
    "Devaluation Provisions for Other Securities & Financial Assets",
    "مؤونة تدنّي سندات أخرى مجمّدة",
    "Provisions pour Dépréciation d’Autres Titres Immobilisés",
    "asset",
    "295"
  ],
  [
    "2955",
    "Devaluation Provisions for Long & Medium Term Loan",
    "مؤونة تدنّي قروض طويلة ومتوسطة الأجل",
    "Provisions pour Dépréciation des Prêts à Long et Moyen Terme",
    "asset",
    "295"
  ],
  [
    "2959",
    "Devaluation Provisions for Other Blocked Financial Assets",
    "مؤونة تدنّي ذمم أخرى مجمّدة",
    "Provisions pour Dépréciation d’Autres Créances Immobilisées",
    "asset",
    "295"
  ],
  [
    "3",
    "Inventory & Goods In Process",
    "المخزون وقيد الصنع",
    "Comptes de Stocks et en Cours",
    "asset",
    None
  ],
  [
    "31",
    "Stock of Raw Materials & Consumables",
    "مخزون مواد أولية وإستهلاكية ولوازم",
    "Stocks – Approvisionnements",
    "asset",
    "3"
  ],
  [
    "311",
    "Stock of Raw Materials",
    "مخزون مواد أولية",
    "Stocks de matières premières",
    "asset",
    "31"
  ],
  [
    "33",
    "Stock of Goods, Works, & Services In Progress",
    "مخزون سلع وأشغال وخدمات قيد الإنجاز",
    "Stocks – en Cours de Production",
    "asset",
    "31"
  ],
  [
    "35",
    "Stock of Manufactured Products",
    "مخزون منتجات وسيطة وتامة الصنع",
    "Stocks – Produits",
    "asset",
    "31"
  ],
  [
    "37",
    "Stock of Goods for Sale",
    "مخزون البضاعة المعدة للبيع",
    "Stocks – Marchandises",
    "asset",
    "31"
  ],
  [
    "39",
    "Provisions For Diminution In Value Of Inventory & Goods In Process",
    "مؤنات هبوط اسعار المخزون وقيد الصنع",
    "Provisions pour Dépréciation des Stocks et en Cours",
    "asset",
    "31"
  ],
  [
    "391",
    "Devaluation Provisions For Raw & Material Stock",
    "مؤونات تدنّي قيمة مخزون المواد الأولية والإستهلاكية",
    "Provisions pour Dépréciation des Approvisionnements",
    "asset",
    "39"
  ],
  [
    "393",
    "Devaluation Provisions For Products In Process",
    "مؤونات تدنّي قيمة مخزون الإنتاج قيد الصنع",
    "Provisions pour Dépréciation des en Cours de Production",
    "asset",
    "39"
  ],
  [
    "395",
    "Devaluation Provisions For Products Stock",
    "مؤونات تدنّي قيمة مخزون الإنتاج التام الصنع",
    "Provisions pour Dépréciation des Produits",
    "asset",
    "39"
  ],
  [
    "397",
    "Devaluation Provisions For Goods For Sale Stock",
    "مؤونات تدنّي قيمة البضاعة المخزونة",
    "Provisions pour Dépréciation des Marchandises",
    "asset",
    "39"
  ],
  [
    "4",
    "Receivables & Payables",
    "حسابات الذمم",
    "Comptes de Tiers",
    "asset",
    None
  ],
  [
    "40",
    "Suppliers",
    "الموردون",
    "Fournisseurs",
    "liability",
    "4"
  ],
  [
    "401",
    "Accounts Payables (Suppliers)",
    "ذمم دائنة (موردو الإستثمار)",
    "Fournisseurs d’Exploitation",
    "liability",
    "40"
  ],
  [
    "4011",
    "Suppliers - Invoices Payable",
    "موردو الاستثمار - فواتير برسم الدفع",
    "Factures Fournisseurs d’Exploitation",
    "liability",
    "401"
  ],
  [
    "4015",
    "Suppliers - Notes Payable",
    "موردو الاستثمار - اوراق دفع",
    "Fournisseurs d’Exploitation - Effets à Payer",
    "liability",
    "401"
  ],
  [
    "4018",
    "Suppliers - Invoices Not Received",
    "موردو الاستثمار - فواتير غير مستلمة",
    "Fournisseurs d’Exploitation – Factures à Recevoir",
    "liability",
    "401"
  ],
  [
    "4019",
    "Discounts Obtained from Suppliers",
    "حسومات مكتسبة من موردي الاستثمار",
    "Fournisseurs d’Exploitation – Rabais et Remises à Obtenir",
    "liability",
    "401"
  ],
  [
    "403",
    "Fixed Assets Suppliers",
    "موردو الاصول الثابتة",
    "Fournisseurs d’Immobilisations",
    "liability",
    "40"
  ],
  [
    "4031",
    "Fixed Assets Suppliers - Invoices Payable",
    "موردو الأصول الثابتة - فواتير برسم الدفع",
    "Factures Fournisseurs d’Immobilisations",
    "liability",
    "403"
  ],
  [
    "4035",
    "Fixed Assets Suppliers - Notes Payable",
    "موردو الأصول الثابتة - اوراق دفع",
    "Fournisseurs d’Immobilisations - Effets à Payer",
    "liability",
    "403"
  ],
  [
    "4038",
    "Fixed Assets Suppliers - Invoices Not Received",
    "موردو الأصول الثابتة - فواتير غير مستلمة",
    "Fournisseurs d’Immobilisations - Factures à Recevoir",
    "liability",
    "403"
  ],
  [
    "4039",
    "Discounts Obtained from Fixed Assets Suppliers",
    "حسومات مكتسبة من موردي الأصول الثابتة",
    "Fournisseurs d’Immobilisations - Rabais et Remises à Obtenir",
    "liability",
    "403"
  ],
  [
    "409",
    "Advances to suppliers",
    "سلفات ودفعات على حساب طلبيات",
    "Avances et Acomptes Versés sur Commandes d’Exploitation",
    "liability",
    "40"
  ],
  [
    "4091",
    "Advance Payments on Purchases",
    "سلفات مدفوعة على طلبيات الاستثمار",
    "Avances Versées sur Commandes d’Achats",
    "liability",
    "409"
  ],
  [
    "4092",
    "Materials Suppliers Accidentally Debtors",
    "موردو الإستثمار مدينون عرضا",
    "Fournisseurs d’Exploitation – Accidents Débiteurs",
    "liability",
    "409"
  ],
  [
    "4093",
    "Fixed Assets Suppliers Accidentally Debtors",
    "موردو الأصول الثابتة مدينون عرضا",
    "Fournisseurs d’Immobilisations – Accidents Débiteurs",
    "liability",
    "409"
  ],
  [
    "41",
    "Debtors (Customers)",
    "الزبائن",
    "Clients",
    "asset",
    "4"
  ],
  [
    "411",
    "Customers - Debtors Account",
    "ذمم مدينة - زبائن",
    "Clients - Comptes Débiteurs",
    "asset",
    "41"
  ],
  [
    "4111",
    "Customers Receivables - Invoices",
    "زبائن مدينون- فواتير برسم التحصيل",
    "Clients Débiteurs",
    "asset",
    "411"
  ],
  [
    "4115",
    "Doubtful Customers",
    "زبائن مشكوك بتحصيل ديونهم",
    "Clients Douteux",
    "asset",
    "411"
  ],
  [
    "4119",
    "Discounts Granted to Customers",
    "حسومات ممنوحة إلى الزبائن",
    "Clients – Rabais et Remises à Accorder",
    "asset",
    "411"
  ],
  [
    "413",
    "Customers Receivables - Bills",
    "أوراق قبض مسحوبة على الزبائن",
    "Clients – Effets à Recevoir",
    "asset",
    "41"
  ],
  [
    "415",
    "Dues From Customers On Works In Process",
    "ذمم مدينة على أشغال قيد الإنجاز",
    "Créances sur Travaux non Encore Facturables",
    "asset",
    "41"
  ],
  [
    "418",
    "Dues From Customers On Invoices In Process",
    "ذمم مدينة على فواتير قيد الإعداد",
    "Factures à Établir",
    "asset",
    "41"
  ],
  [
    "419",
    "Customers Credit Advances on Placed Orders",
    "سلفات ومقبوضات على حساب طلبيات قيد التنفيذ",
    "Avances et Acomptes Reçus sur Commandes en Cours",
    "asset",
    "41"
  ],
  [
    "4191",
    "Advances Received on Sales Orders",
    "سلفات مقبوضة من الزبائن على طلبيات للتنفيذ",
    "Acomptes Reçus sur Commandes de Ventes",
    "asset",
    "419"
  ],
  [
    "4192",
    "Customers Accidentally Creditors",
    "حسابات زبائن أرصدتها دائنة عرضا",
    "Clients Accidentellement Créditeurs",
    "asset",
    "419"
  ],
  [
    "42",
    "Personnel",
    "المستخدمون",
    "Personnel",
    "asset",
    "4"
  ],
  [
    "421",
    "Personnel Accounts Payable",
    "مستحقات للمستخدمين",
    "Rémunérations Dues au Personnel – Créditeurs",
    "asset",
    "42"
  ],
  [
    "4211",
    "Salaries & Wages due to Personnel",
    "مستحقات رواتب وأجور للمستخدمين والعمّال",
    "Salaires dus au Personnel",
    "asset",
    "421"
  ],
  [
    "4219",
    "Other dues to Personnel",
    "مستحقات أخرى متوجّبة للمستخدمين والعمّال",
    "Autres Rémunérations dues au Personnel",
    "asset",
    "421"
  ],
  [
    "428",
    "Personnel Accounts Receivable",
    "ذمم وسلفات على المستخدمين",
    "Personnel – Comptes Débiteurs",
    "asset",
    "42"
  ],
  [
    "4281",
    "Loans to Personnel",
    "سلفات مدفوعة للمستخدمين",
    "Prêts Accordés au Personnel",
    "asset",
    "428"
  ],
  [
    "4282",
    "Garnishments on Personnel Dues",
    "حجوزات على المستخدمين",
    "Oppositions sur Rémunérations du Personnel",
    "asset",
    "428"
  ],
  [
    "4289",
    "Other Receivables from Personnel",
    "ذمم أخرى مستحقّة على المستخدمين",
    "Autres Créances au Personnel",
    "asset",
    "428"
  ],
  [
    "43",
    "Social Security",
    "مؤسسات الضمان الاجتماعي",
    "Organismes Sociaux",
    "asset",
    "4"
  ],
  [
    "431",
    "Social Security Fund - Creditors Accounts",
    "ذمم دائنة لحساب الضمان الاجتماعي",
    "Dettes envers les Organismes Sociaux",
    "asset",
    "43"
  ],
  [
    "4311",
    "Social Security - Payable Dues",
    "الضمان الاجتماعي - اشتراكات متوجبة",
    "Sécurité Sociale – Cotisations à Payer",
    "asset",
    "431"
  ],
  [
    "4315",
    "Social Security - Notes Payable",
    "الضمان الاجتماعي - اوراق دفع",
    "Sécurité Sociale – Effets à Payer",
    "asset",
    "431"
  ],
  [
    "4318",
    "Social Security - Charges to be Accounted for",
    "الضمان الاجتماعي - أعباء يجب لحظها",
    "Sécurité Sociale – Charges à Constater",
    "asset",
    "431"
  ],
  [
    "438",
    "Social Security Receivables",
    "ذمم مدينة على الضمان الاجتماعي",
    "Créances sur Sécurité Sociale",
    "asset",
    "43"
  ],
  [
    "44",
    "Government & Public Institutions",
    "الدولة والمؤسسات العامة",
    "État et Collectivités Publiques",
    "asset",
    "4"
  ],
  [
    "441",
    "Taxes Due on Operations",
    "ضرائب متوجبة على الإستثمار",
    "Impôts dus Sur l’exploitation",
    "asset",
    "44"
  ],
  [
    "4411",
    "Taxes & Duties (Except Income Tax)",
    "ضرائب ورسوم متوجبة (ما عدا ضريبة الأرباح)",
    "Impôts et Taxes – (Impôt sur le Revenu Exclus)",
    "asset",
    "44"
  ],
  [
    "4415",
    "Taxes & Duties - Notes Payable",
    "ضرائب ورسوم متوجبة - أوراق دفع",
    "Impôts et Taxes – Effets à Payer",
    "asset",
    "44"
  ],
  [
    "4418",
    "Taxes & Duties - Charges to be Accounted for",
    "ضرائب ورسوم متوجبة - أعباء يجب لحظها",
    "Impôts et Taxes – Charges à Constater",
    "asset",
    "44"
  ],
  [
    "442",
    "Value Added Tax Accounts",
    "الدولة والمؤسسات العامة - الضريبة على القيمة المضافة",
    "Taxe sur la Valeur Ajoutée – TVA",
    "asset",
    "44"
  ],
  [
    "4425",
    "Value Added Tax - Debtor/Creditor Balance",
    "ضريبة القيمة المضافة - رصيد مدين أو دائن",
    "TVA - Solde Débiteurs ou Créditeur",
    "asset",
    "44"
  ],
  [
    "4425.1",
    "Value Added Tax - To Be Paid",
    "الضريبة المتوجب دفعها على القيمة المضافة",
    "TVA à payer",
    "asset",
    "4425"
  ],
  [
    "4426.2",
    "Value Added Tax - On Fixed Assets Purchases",
    "ضريبة القيمة المضافة - مدفوعة عن أصول ثابتة",
    "TVA - Sur Achats d'Immobilisations",
    "asset",
    "4425"
  ],
  [
    "4426.6",
    "Value Added Tax - On Purchases & Charges",
    "ضريبة القيمة المضافة - مدفوعة عن مشتريات او مصاريف",
    "TVA - Sur Achats & Charges",
    "asset",
    "4425"
  ],
  [
    "4427",
    "Value Added Tax - Collected on Revenues",
    "ضريبة القيمة المضافة - محصّلة من الإيرادات",
    "TVA - Percue sur Produits",
    "asset",
    "4425"
  ],
  [
    "4428.3",
    "Value Added Tax - Payment To Be Returned",
    " تسديدات للضريبة على قيم مضافة مطلوب إسترجاعها",
    "TVA à récupérer",
    "asset",
    "4425"
  ],
  [
    "4429",
    "Value Added Tax - Due for Refund",
    "ضريبة القيمة المضافة - متوجّبة الأسترداد",
    "TVA - à Recupérer",
    "asset",
    "4425"
  ],
  [
    "443",
    "Non-Operational Tax",
    "ضرائب متوجّبة خارج الإستثمار",
    "Impôts Hors Exploitation",
    "asset",
    "4425"
  ],
  [
    "4431",
    "Income Tax on Net Operating Profits",
    "الضريبة على أرباح الإستثمار",
    "Impôts sur les Bénéfices",
    "asset",
    "443"
  ],
  [
    "4432",
    "Tax on Fixed Assets Disposal or Revaluation Profits",
    "الضريبة على أرباح التحسين والتفرّغ عن أصول",
    "Impôts sur Cessions et Révalorisations d’Immobilisations",
    "asset",
    "443"
  ],
  [
    "4435",
    "Tax on Holding & Off-Shore Companies",
    "الضريبة على شركات الهولدنغ والأوف شور",
    "Impôts sur Sociétés Holdings et Off-Shore",
    "asset",
    "443"
  ],
  [
    "445",
    "Government & Public Services - Credit Account",
    "الدولة والمؤسّسات العامة - ذمم دائنة",
    "Autres Dettes envers l’État et les Collectivités Publiques",
    "asset",
    "4425"
  ],
  [
    "449",
    "Government & Public Services - Debit Account",
    "الدولة والمؤسّسات العامة - ذمم مدينة",
    "Créances sur l’État et les Collectivités Publiques",
    "asset",
    "4425"
  ],
  [
    "45",
    "Partners",
    "الشركاء",
    "Associés",
    "asset",
    "44"
  ],
  [
    "451",
    "Related Companies Accounts",
    "الحسابات للشركات المترابطة - شركات شقيقة",
    "Sociétés Apparentées",
    "asset",
    "45"
  ],
  [
    "4511",
    "Related Companies Debtor Accounts",
    "الحسابات المدينة للشركات المترابطة (الشقيقة)",
    "Sociétés Apparentées – Comptes Débiteurs",
    "asset",
    "451"
  ],
  [
    "4511.1",
    "Mother Company Debtor Account",
    "الحساب المدين للشركة الأم",
    "Société Mère – Compte Débiteur",
    "asset",
    "4511"
  ],
  [
    "4511.2",
    "Affiliated Companies Debtor Accounts",
    "الحساب المدين للشركات التابعة",
    "Sociétés Dépendantes – Comptes Débiteurs",
    "asset",
    "4511"
  ],
  [
    "4511.3",
    "Associated Companies Debtor Accounts",
    "الحساب المدين للشركات المشاركة",
    "Sociétés Associées – Comptes Débiteurs",
    "asset",
    "4511"
  ],
  [
    "4511.4",
    "Companies Affiliated to Different Holdings – Debit Accounts",
    "الحساب المدين للشركات الداخلة في عدة مجموعات",
    "Sociétés Multigroupes – Comptes Débiteurs",
    "asset",
    "4511"
  ],
  [
    "4512",
    "Related Companies Creditor Accounts",
    "الحسابات الدائنة للشركات المترابطة - شركات شقيقة",
    "Sociétés Apparentées – Comptes Créditeurs",
    "asset",
    "451"
  ],
  [
    "4512.1",
    "Mother Company Creditor Account",
    "الحساب الدائن للشركة الأم",
    "Société Mère – Compte Créditeur",
    "asset",
    "4512"
  ],
  [
    "4512.2",
    "Affiliated Companies Creditor Accounts",
    "الحساب الدائن للشركات التابعة",
    "Sociétés Dépendantes – Comptes Créditeurs",
    "asset",
    "4512"
  ],
  [
    "4512.3",
    "Associated Companies Creditor Accounts",
    "الحساب الدائن للشركات المشاركة",
    "Sociétés Associées – Comptes Créditeurs",
    "asset",
    "4512"
  ],
  [
    "4512.4",
    "Companies Affiliated to Different Holdings – Credit Accounts",
    "الحساب الدائن للشركات الداخلة في عدة مجموعات",
    "Sociétés Multigroupes – Comptes Créditeurs",
    "asset",
    "4512"
  ],
  [
    "4515.1",
    "Partners & Other Related Companies - Debit Accounts",
    "شركاء - حسابات جارية ذات أرصدة مدينة",
    "Associés – Comptes Courants Débiteurs",
    "asset",
    "451"
  ],
  [
    "4515.2",
    "Partners & Other Related Companies - Credit Accounts",
    "شركاء - حسابات جارية ذات أرصدة دائنة",
    "Associés – Comptes Courants Créditeurs",
    "asset",
    "451"
  ],
  [
    "4518.1",
    "Joint Ventures - Debtor Balances",
    "عمليات مشتركة - ذات أرصدة مدينة",
    "Opérations en Commun – Solde Débiteur",
    "asset",
    "451"
  ],
  [
    "4518.2",
    "Joint Ventures - Creditor Balances",
    "عمليات مشتركة - ذات أرصدة دائنة",
    "Opérations en Commun – Solde Créditeur",
    "asset",
    "451"
  ],
  [
    "453",
    "Dividends Payable",
    "مساهمون - انصبة ارباح برسم الدفع",
    "Dividendes à Payer",
    "asset",
    "45"
  ],
  [
    "455",
    "Shareholders/Partners Payables On Capital",
    "مساهمون - الذمم الدائنة على رأس المال",
    "Actionnaires/Associés – Comptes Créditeurs",
    "asset",
    "45"
  ],
  [
    "4551",
    "Shareholders/Partners - Contributions to the Capital",
    "مساهمون/شركاء - حسابات المقدمات للشركة",
    "Actionnaires/Associés – Comptes d’Apport en Société",
    "asset",
    "455"
  ],
  [
    "4552",
    "Shareholders/Partners - Re-imbursement of the Capital",
    "مساهمون/شركاء - حسابات إسترداد رأس المال",
    "Actionnaires/Associés – Capital à Rembourser",
    "asset",
    "455"
  ],
  [
    "4557",
    "Shareholders/Partners - Other Payables on Capital",
    "مساهمون/شركاء - ذمم أخرى دائنة على رأس المال",
    "Actionnaires/Associés – Autres Dûs sur Capital",
    "asset",
    "455"
  ],
  [
    "459",
    "Shareholders/Partners Receivables On Capital",
    "مساهمون - الذمم المدينة على رأس المال",
    "Créances sur Actionnaires/Associés",
    "asset",
    "45"
  ],
  [
    "4591",
    "Shareholders - Subscribed/Un-Called Capital",
    "مساهمون - المكتتب غير المستدعى من رأس المال",
    "Actionnaires – Capital Souscrit Non Appelé",
    "asset",
    "459"
  ],
  [
    "4592",
    "Shareholders - Subscribed/Called/Unpaid Capital",
    "مساهمون - المكتتب المستدعى وغير المدفوع من رأس المال",
    "Actionnaires – Capital Souscrit Appelé Non Versé",
    "asset",
    "459"
  ],
  [
    "4597",
    "Shareholders/Partners - Other Receivables on Capital",
    "مساهمون/شركاء - ذمم أخرى مدينة على رأس المال",
    "Actionnaires/Associés – Autres Créances sur Capital",
    "asset",
    "459"
  ],
  [
    "46",
    "Miscellaneous Accounts Receivable & Payable",
    "ذمم مختلفة",
    "Autres Débiteurs et Créditeurs",
    "asset",
    "44"
  ],
  [
    "4611",
    "Payables on Consignments",
    "ذمم دائنة متعلّقة بالعبوات والمعدّات",
    "Dettes pour Emballages et Matériels Consignés",
    "asset",
    "46"
  ],
  [
    "4619",
    "Other Operating Creditor Accounts",
    "حسابات دائنة مختلفة - إستثمار",
    "Comptes Créditeurs Divers – Exploitation",
    "asset",
    "46"
  ],
  [
    "463",
    "Payables on Financial Fixed Assets",
    "أقساط برسم الدفع على أصول ثابتة مالية",
    "Versements Restant à Effectuer sur Immobilisations Financières",
    "asset",
    "46"
  ],
  [
    "465",
    "Sundry Non-Operating Accounts Payable",
    "دائنون مختلفون خارج الإستثمار",
    "Autres Créditeurs Divers – Hors Exploitation",
    "asset",
    "46"
  ],
  [
    "4681",
    "Receivables on Consignments",
    "ذمم مدينة متعلّقة بالعبوات والمعدّات",
    "Créances pour Emballages et Matériels à Rendre",
    "asset",
    "46"
  ],
  [
    "4689",
    "Other Operating Debtor Accounts",
    "حسابات مدينة مختلفة - إستثمار",
    "Autres Comptes Débiteurs Divers – Exploitation",
    "asset",
    "46"
  ],
  [
    "4691",
    "Receivables on Disposals of Fixed Assets & Financial Deeds",
    "ذمم مدينة على بيع اصول ثابتة وسندات توظيف",
    "Créances sur Cession d’Immobilisations et Valeurs Mobilières de Placement",
    "asset",
    "46"
  ],
  [
    "4699",
    "Other Non-Operating Debtor Accounts",
    "مدينون مختلفون - خارج الإستثمار",
    "Autres Comptes Débiteurs Divers – Hors Exploitation",
    "asset",
    "46"
  ],
  [
    "47",
    "PRE-PAYMENTS & ACCRUALS",
    "حسابات التسوية",
    "Comptes de Régularisation",
    "asset",
    "44"
  ],
  [
    "471",
    "Deferred Charges",
    "الأعباء الواجب توزيعها على عدة دورات",
    "Charges à Répartir sur Plusieurs Exercices",
    "asset",
    "47"
  ],
  [
    "4711",
    "Pre-Operating Expenses",
    "أعباء ما قبل الإستثمار",
    "Frais de Pré-Exploitation",
    "asset",
    "471"
  ],
  [
    "4712",
    "Major Repairs to be Amortized",
    "التصليحات الكبيرة الواجب إستهلاكها",
    "Grosses Réparations à Amortir",
    "asset",
    "471"
  ],
  [
    "4713",
    "Bonds Settlement Premium",
    "علاوات تسديد السندات",
    "Primes de Remboursement des Obligations",
    "asset",
    "471"
  ],
  [
    "4719",
    "Other Deferred Charges",
    "اعباء أخرى واجب توزيعها على عدة دورات",
    "Autres Charges à Répartir sur Plusieurs Exercices",
    "asset",
    "471"
  ],
  [
    "472",
    "Prepaid Charges",
    "اعباء محتسبة مسبقا",
    "Charges Constatées d’Avance",
    "asset",
    "47"
  ],
  [
    "473",
    "Accrued Income",
    "ايرادات محتسبة مسبقا",
    "Produits Constatés d’Avance",
    "asset",
    "47"
  ],
  [
    "474",
    "Accrued Unpaid Charges",
    "اعباء مستحقة وغير مدفوعة",
    "Frais à Payer",
    "asset",
    "47"
  ],
  [
    "475",
    "Exchange Difference - Liability",
    "فروقات صرف - خصوم",
    "Écarts de Conversion – Passif",
    "asset",
    "47"
  ],
  [
    "476",
    "Exchange Difference - Asset",
    "فروقات صرف - أصـول",
    "Écarts de Conversion – Actif",
    "asset",
    "47"
  ],
  [
    "48",
    "Temporary & Suspense Accounts",
    "الحسابات المؤقّتة وقيد التسوية",
    "Comptes d’Attente et à Régulariser",
    "asset",
    "44"
  ],
  [
    "481",
    "Pending & Regularization Accounts",
    "الحسابات التوزيع الدوري للأعباء",
    "Comptes d’Attente et à Régulariser",
    "asset",
    "48"
  ],
  [
    "482",
    "Periodic Distribution of Revenues",
    "الحسابات التوزيع الدوري للإيرادات",
    "Distribution Périodique des Revenues",
    "asset",
    "48"
  ],
  [
    "49",
    "Provisions For Diminution In Value of Receivables & Payables",
    "مؤونات لمواجهة هبوط قيم حسابات الذمم",
    "Provisions pour Dépréciation des Comptes de Titres",
    "asset",
    "44"
  ],
  [
    "491",
    "Provisions for Customers Bad Debts",
    "مؤونات تدني قيم حسابات الزبائن",
    "Provisions pour Dépréciation des Créances Clients",
    "asset",
    "49"
  ],
  [
    "495",
    "Provisions for Shareholders/Partners Bad Debts",
    "مؤونات تدني قيم حسابات الشركاء",
    "Provisions pour Dépréciation des Comptes Associés",
    "asset",
    "49"
  ],
  [
    "496",
    "Sundry Debtors Devaluation Provisions",
    "مؤونات هبوط قيم حسابات الذمم المدينة المختلفة",
    "Provisions pour Dévaluation de Créances Diverses",
    "asset",
    "49"
  ],
  [
    "4968",
    "Provisions for Other Operating Bad Debts",
    "مؤونات تدني قيم ذمم إستثمار مدينة متفرّقة",
    "Provisions pour Débiteurs Divers – Exploitation",
    "asset",
    "496"
  ],
  [
    "4969",
    "Provisions for Other Non-Operating Bad Debts",
    "مؤونات تدني قيم ذمم مدينة - خارج الإستثمار",
    "Provisions pour Débiteurs Divers – Hors Exploitation",
    "asset",
    "496"
  ],
  [
    "498",
    "Bad Debts Due to Bankruptcy",
    "مؤونات خسائر ديون عند إعلان الإفلاس",
    "Provisions pour Pertes de Créances en Cas de Faillite",
    "asset",
    "49"
  ],
  [
    "4981",
    "Provisions for Losses on Bankrupt Clients Accounts",
    "مؤونات خسائر ديون زبائن عند إعلان الإفلاس",
    "Provisions pour Pertes sur Clients en Faillite",
    "asset",
    "498"
  ],
  [
    "4985",
    "Provisions for Losses on Bankrupt Partners Accounts",
    "مؤونات خسائر ديون شركاء عند إعلان الإفلاس",
    "Provisions pour Pertes sur Associés en Faillite",
    "asset",
    "498"
  ],
  [
    "4986.8",
    "Provisions for losses on Operational Bankrupt Debtors",
    "مؤونات خسائر ديون إستثمار متفرّقة - (إفلاس)",
    "Provisions pour Débiteurs Divers en Faillite – Exploitation",
    "asset",
    "498"
  ],
  [
    "4986.9",
    "Provisions for losses on Non-Operational Bankrupt Debtors",
    "مؤونات خسائر ديون خارج الإستثمار - (إفلاس)",
    "Provisions pour Débiteurs Divers en Faillite – Hors Exploitation",
    "asset",
    "498"
  ],
  [
    "5",
    "Financial Accounts",
    "الحسابات المالية",
    "Comptes Financiers",
    "asset",
    None
  ],
  [
    "50",
    "Marketable Securities",
    "سندات توظيف",
    "Valeurs Mobilières de Placement",
    "asset",
    "5"
  ],
  [
    "501",
    "Treasury Shares",
    "اسهم صادرة عن الشركة ومعاد شراؤها من قبلها",
    "Actions Propres Rachetées par l’Entreprise",
    "asset",
    "50"
  ],
  [
    "502",
    "Bonds with Shares Acquisition Rights",
    "سندات تمنح حامليها حق الملكية",
    "Bons & Coupons Emis Par La Socièté",
    "asset",
    "50"
  ],
  [
    "505",
    "Bonds and Coupons Issued by The Company",
    "سندات دين وقصائم صادرة عن الشركة",
    "Bons Avec Droit d'Acquisition d'Actions",
    "asset",
    "50"
  ],
  [
    "506",
    "Bonds With Creditors Rights",
    "سندات تمنح حامليها حقوق الدائنين",
    "Bons Avec Droit de Créditeurs",
    "asset",
    "50"
  ],
  [
    "51",
    "Financial Institutions",
    "المؤسسات المالية",
    "Établissements Financiers",
    "asset",
    "5"
  ],
  [
    "511",
    "Cheques & Coupons under Collection",
    "شيكات وقسائم برسم التحصيل لدى المصارف",
    "Chèques et Coupons à Encaisser",
    "asset",
    "51"
  ],
  [
    "512",
    "Banks Debtor Accounts",
    "مصارف حسابات مدينة",
    "Banques – Comptes Débiteurs",
    "asset",
    "51"
  ],
  [
    "5121",
    "Banks - Current Debtor Accounts",
    "مصارف - حسابات جارية مدينة",
    "Banques – Comptes Courants Débiteurs",
    "asset",
    "512"
  ],
  [
    "5122",
    "Banks - Facilities Accidentally Debtor",
    "حسابات تسهيلات مصرفية أرصدتها مدينة عرضا",
    "Banques – Soldes Facilités Accidentels Débiteurs",
    "asset",
    "512"
  ],
  [
    "5123",
    "Banks - Term Deposits Accounts",
    "مصارف - حسابات مدينة لأجل",
    "Banques – Dépôts à Terme",
    "asset",
    "512"
  ],
  [
    "519",
    "Credit Establishments",
    "مؤسّسات التمويل",
    "Etablissements de Crédits",
    "asset",
    "51"
  ],
  [
    "5191",
    "Banks & Financial Establishments Facilities",
    "مصارف - تسهيلات وحسابات مكشوفة",
    "Banques et Établissements Financiers – Comptes Facilités",
    "asset",
    "519"
  ],
  [
    "5192",
    "Banks Current Accounts Accidentally Creditor",
    "حسابات مصرفية جارية أرصدتها دائنة عرضا",
    "Banques – Comptes Courants Accidentels Créditeurs",
    "asset",
    "519"
  ],
  [
    "53",
    "Cash",
    "الصندوق",
    "Caisse",
    "asset",
    "5"
  ],
  [
    "531",
    "CASH ON HAND",
    "صندوق النقدية",
    "Caisse",
    "asset",
    "53"
  ],
  [
    "58",
    "Intercompany",
    "التحويلات الداخلية",
    "Virements Internes",
    "asset",
    "5"
  ],
  [
    "59",
    "Provisions",
    "مؤنات هبوط اسعار سندات التوظيف",
    "Provisions pour Dépréciation des Valeurs Mobilières de Placement",
    "asset",
    "5"
  ],
  [
    "6",
    "Costs & Expenses",
    "حسابات الأعباء",
    "Comptes de Charges",
    "expense",
    None
  ],
  [
    "60",
    "Purchase & Variation of Inventory",
    "مشتريات البضاعة وقيمة التغيير في المخزون",
    "Achats de Marchandises et Variations des Stocks",
    "expense",
    "6"
  ],
  [
    "601",
    "Purchases",
    "مشتريات البضاعة",
    "Achats de Marchandises",
    "expense",
    "60"
  ],
  [
    "6011",
    "Purchase of Goods",
    "شراء بضـاعة",
    "Achats de Marchandises",
    "expense",
    "601"
  ],
  [
    "6012",
    "Purchase of Packing Materials for Goods",
    "شراء عبوات للبضاعة",
    "Achats d’Emballages pour Marchandises",
    "expense",
    "601"
  ],
  [
    "6018",
    "Charges & Expenses on Goods Purchasing",
    "نفقات إضافية على شراء بضاعة وعبوات",
    "Frais Accessoires sur Achats de Marchandises et Emballages",
    "expense",
    "601"
  ],
  [
    "6019",
    "Discounts Obtained on Purchased Goods",
    "حسومات مكتسبة على شراء بضاعة",
    "Rabais, Remises et Ristournes sur Marchandises",
    "expense",
    "601"
  ],
  [
    "605",
    "Variation of Inventory",
    "التغيير في مخزون البضاعة",
    "Variation des stocks de marchandises",
    "expense",
    "60"
  ],
  [
    "6051",
    "Stock of Goods - Opening Stock",
    "مخزون البضاعة - أول المدّة",
    "Stock Marchandises – Début de Période",
    "expense",
    "605"
  ],
  [
    "6052",
    "Stock of Goods - Closing Stock",
    "مخزون البضاعة - آخر المدّة",
    "Stock Marchandises – Fin de Période",
    "expense",
    "605"
  ],
  [
    "61",
    "Purchase of Raw Materials  & Consumables",
    "مواد اولية واستهلاكية مستخدمة",
    "Achats d’Approvisionnements et Variation des Stocks",
    "expense",
    "6"
  ],
  [
    "611",
    "Raw materials & Consumables Purchases",
    "مشتريات المواد الأولية والإستهلاكية",
    "Achats d’Approvisionnements",
    "expense",
    "61"
  ],
  [
    "6111",
    "Purchase of Raw Materials",
    "شراء مواد أولية",
    "Achats de Matières Premières",
    "expense",
    "611"
  ],
  [
    "6112",
    "Purchase of Manufacturing Consumables",
    "شراء مواد ولوازم استهلاكية للإنتاج",
    "Achats de Matières et Fournitures Consommables",
    "expense",
    "611"
  ],
  [
    "6113",
    "Purchase of Packing Materials for Products",
    "شراء عـبوات للمنتجات",
    "Achats d’Emballages pour Produits",
    "expense",
    "611"
  ],
  [
    "6118",
    "Charges & Expenses on Raw Material & Consumables Purchasing",
    "نفقات إضافية على شراء مواد أولية واستهلاكية",
    "Frais Accessoires sur Achats d’Approvisionnements",
    "expense",
    "611"
  ],
  [
    "6119",
    "Discounts Obtained On Purchased R.M & Consumables",
    "حسومات مكتسبة على شراء مواد أولية وإستهلاكية",
    "Rabais, Remises et Ristournes sur Approvisionnements",
    "expense",
    "611"
  ],
  [
    "615",
    "Variation Raw Materials & Consumables Inventory",
    "التغيير في مخزون المواد الاولية والاستهلاكية",
    "Variation des Stocks d’Approvisionnements",
    "expense",
    "61"
  ],
  [
    "6151",
    "Stock of Raw & Other Materials - Opening Stock",
    "مخزون المواد الاولية والاستهلاكية - أول المدّة",
    "Stock Approvisionnements – Début de Période",
    "expense",
    "615"
  ],
  [
    "6152",
    "Stock of Raw & Other Material - Closing Stock",
    "مخزون المواد الاولية والاستهلاكية - آخر المدّة",
    "Stock Approvisionnements – Fin de Période",
    "expense",
    "615"
  ],
  [
    "62",
    "Other Charges & Disbursments",
    "اعباء خارجية اخرى",
    "Autres Charges Externes",
    "expense",
    "6"
  ],
  [
    "621",
    "Costs Related to Sub Contracts",
    "مشتريات من ملتزمين ثانويين",
    "Achats de Sous-traitance",
    "expense",
    "62"
  ],
  [
    "6211",
    "Purchase of Works from Sub-Contractors",
    "مشتريات من ملتزمين ثانويين - أشغال",
    "Sous-Traitance – Travaux",
    "expense",
    "621"
  ],
  [
    "6212",
    "Purchase of Services from Sub-Contractors",
    "مشتريات من ملتزمين ثانويين - خدمات",
    "Sous-Traitance – Services",
    "expense",
    "621"
  ],
  [
    "6219.1",
    "Discounts Obtained On Purchased Works",
    "حسومات مكتسبة على مشتريات أشغال",
    "Rabais et Remises Obtenus sur Travaux",
    "expense",
    "621"
  ],
  [
    "6219.2",
    "Discounts Obtained On Purchased Services",
    "حسومات مكتسبة على مشتريات خدمات",
    "Rabais et Remises Obtenus sur Services",
    "expense",
    "621"
  ],
  [
    "625",
    "Leasing & Patents Cost",
    "الاتاوى",
    "Redevances",
    "expense",
    "62"
  ],
  [
    "6250",
    "Leasing, Patent Fees & Royalties",
    "أتـاوى وعائدات مدفوعة",
    "Redevances",
    "expense",
    "625"
  ],
  [
    "626",
    "External Services",
    "الخدمات الخارجية",
    "Services Extérieurs",
    "expense",
    "62"
  ],
  [
    "6261.1",
    "Assets & Goods Transportation Charges",
    "نفقات نقل موجودات وبضائع",
    "Frais de Transport de Biens",
    "expense",
    "626"
  ],
  [
    "6261.2",
    "Personnel Transportation Charges",
    "نفقات نقل المستخدمين",
    "Frais de Transport Collectif du Personnel",
    "expense",
    "626"
  ],
  [
    "6261.5",
    "Post & Telecommunication Charges",
    "نفقات البريد والإتّصالات",
    "Frais de Postes et Télécommunications",
    "expense",
    "626"
  ],
  [
    "6262",
    "Equipment Maintenance & Repair",
    "صيانة وتصليح التجهيزات",
    "Entretien et Réparation",
    "expense",
    "626"
  ],
  [
    "6263.1",
    "Rental Fees",
    "بدلات الإيجار",
    "Loyers",
    "expense",
    "626"
  ],
  [
    "6263.2",
    "Rental Charges (Condominium Charges)",
    "أعباء تأجيرية (أعباء الأقسام المشتركة)",
    "Charges Locatives",
    "expense",
    "626"
  ],
  [
    "6263.3",
    "Drinking Water Expenses",
    "مصاريف مياه الشفة",
    "Eau",
    "expense",
    "626"
  ],
  [
    "6263.4",
    "Lighting Expenses",
    "مصاريف كهرباء الإنارة",
    "Électricité",
    "expense",
    "626"
  ],
  [
    "6263.5",
    "Building Maintenance Expenses",
    "مصاريف صيانة الأبنية",
    "Entretien des Bâtiments",
    "expense",
    "626"
  ],
  [
    "6263.9",
    "Miscellaneous Expense on Buildings",
    "مصاريف متفرّقة على الأبنية",
    "Charges Diverses sur Bâtiments",
    "expense",
    "626"
  ],
  [
    "6264.1",
    "Entertainment Expenses",
    "مصاريف تشريفات وضيافة",
    "Réceptions",
    "expense",
    "626"
  ],
  [
    "6264.2",
    "Travel & Accommodation Expenses",
    "مصاريف إنتقال وسفر وإقامة",
    "Déplacements, Voyages et Logements",
    "expense",
    "626"
  ],
  [
    "6264.3",
    "Personnel Meals Expenses",
    "مصاريف إطعام المستخدمين",
    "Restauration du Personnel",
    "expense",
    "626"
  ],
  [
    "6264.4",
    "Representation Fees",
    "مصاريف تمثيل",
    "Frais de Représentation",
    "expense",
    "626"
  ],
  [
    "6265.1",
    "Interim Staff & Manpower Fees",
    "أتعاب مستخدمين موّقتين",
    "Personnel Intérimaire",
    "expense",
    "626"
  ],
  [
    "6265.2",
    "Commissions Paid to Agents",
    "عمولات مدفوعة للوسطاء",
    "Rémunérations d’Intermédiaires",
    "expense",
    "626"
  ],
  [
    "6265.3",
    "Lawyers, Consultants & Experts Fees",
    "أتعاب محامين ومستشارين وخبراء",
    "Honoraires Avocats, Consultants, Experts",
    "expense",
    "626"
  ],
  [
    "6265.4",
    "Recruitment Fees",
    "أتعاب خدمات التوظيف",
    "Frais Services de Recrutement",
    "expense",
    "626"
  ],
  [
    "6266.1",
    "Training Seminars Fees & Charges",
    "أعباء وأتعاب إعداد وتدريب",
    "Frais et Honoraires de Formation",
    "expense",
    "626"
  ],
  [
    "6266.2",
    "Documentation & Subscriptions",
    "مصاريف توثيق وإشتراكات",
    "Documentation",
    "expense",
    "626"
  ],
  [
    "6267",
    "RESEARCH & STUDIES FEES",
    "مصاريف دراسات وبحوث",
    "Études et Recherches",
    "expense",
    "626"
  ],
  [
    "6268",
    "Insurance Premium",
    "أقساط تأمين",
    "Primes d’Assurances",
    "expense",
    "626"
  ],
  [
    "6269.1",
    "Medical Care",
    "خدمات عناية صحية",
    "Services de Santé",
    "expense",
    "626"
  ],
  [
    "6269.2",
    "Financial Charges (on Bills & other)",
    "أعباء مالية (على سندات وخلافه)",
    "Frais Financiers (sur Effets ou Autres)",
    "expense",
    "626"
  ],
  [
    "6269.3",
    "Advertising & Publicity",
    "مصاريف دعاية وإعلان",
    "Frais de Publicité",
    "expense",
    "626"
  ],
  [
    "6269.4",
    "Stationery & Office Supplies",
    "مصاريف قرطاسية ولوازم مكتبية",
    "Fournitures de Bureau",
    "expense",
    "626"
  ],
  [
    "6269.9",
    "Other Miscellaneous External Services",
    "خدمات خارجية أخرى متفرّقة",
    "Autres Services Extérieurs",
    "expense",
    "626"
  ],
  [
    "63",
    "Personnel Charges",
    "اعباء المستخدمين",
    "Charges des Personnels",
    "expense",
    "6"
  ],
  [
    "631",
    "Salaries & Wages",
    "رواتب وأجور المستخدمين",
    "Rémunérations du Personnel",
    "expense",
    "63"
  ],
  [
    "6311",
    "Staff Salaries",
    "رواتب المستخدمين",
    "Salaires",
    "expense",
    "631"
  ],
  [
    "6312",
    "Manpower Wages",
    "أجور العمّال",
    "Appointements",
    "expense",
    "631"
  ],
  [
    "6314",
    "Commissions Paid to Personnel",
    "عمولات مدفوعة للمستخدمين",
    "Commissions de Base",
    "expense",
    "631"
  ],
  [
    "6316",
    "Partners/Managers Remunerations",
    "بدلات مدفوعة لمديرين ذوي أغلبية في المؤسّسة",
    "Rémunération des Gérants Majoritaires",
    "expense",
    "631"
  ],
  [
    "6317",
    "Directors Remunerations",
    "بدلات مدفوعة لأعضاء مجلس الإدارة",
    "Rémunération des Administrateurs",
    "expense",
    "631"
  ],
  [
    "6319.1",
    "Personnel Transport Allowances",
    "بدلات نقل وإنتقال للمستخدمين",
    "Allocations de Transport",
    "expense",
    "631"
  ],
  [
    "6319.2",
    "Personnel Meal Allowances",
    "بدلات طعام للمستخدمين",
    "Allocations de Restauration",
    "expense",
    "631"
  ],
  [
    "6319.3",
    "Personnel Training Allowances",
    "بدلات إعداد وتدريب للمستخدمين",
    "Allocations de Formation",
    "expense",
    "631"
  ],
  [
    "6319.4",
    "Personnel Medical & Other Insurance",
    "تأمينات صحية وخلافها للمستخدمين",
    "Allocations Médicales",
    "expense",
    "631"
  ],
  [
    "6319.5",
    "Scholarships to the Personnel & their Child.",
    "منح تعليم للمستخدمين وأولادهم",
    "Allocations Scolaires",
    "expense",
    "631"
  ],
  [
    "6319.9",
    "Other Sundry Personnel Allowances",
    "بدلات أخرى متفرّقة للمستخدمين",
    "Allocations Diverses",
    "expense",
    "631"
  ],
  [
    "635",
    "Social Security Charges",
    "أعباء الضمان الإجتماعي",
    "Charges Sociales",
    "expense",
    "63"
  ],
  [
    "6351",
    "Social Security Fund Contributions",
    "اشتراكات فروع الضمان الاجتماعي",
    "Cotisations a la C.N.S.S",
    "expense",
    "63"
  ],
  [
    "6355",
    "End of Service Indemnities Provisions",
    "فروقات تعويضات نهاية الخدمة",
    "Provisions pour Indemnities de Fin de Service",
    "expense",
    "63"
  ],
  [
    "64",
    "Fees & Taxes",
    "ضرائب ورسوم ومدفوعات مماثلة",
    "Impôts, Taxes et Versements Assimilés",
    "expense",
    "6"
  ],
  [
    "641",
    "Income Tax On Salaries & Wages",
    "ضرائب ورسوم على الأجور والأتعاب",
    "Impôts sur Salaires et Rémunérations",
    "expense",
    "64"
  ],
  [
    "642",
    "Municipal Taxes & Duties",
    "ضرائب ورسوم بلديّة",
    "Impôts et Taxes Municipaux",
    "expense",
    "64"
  ],
  [
    "643",
    "Excise Tax",
    "ضرائب على المبيعات غير قابلة للإسترداد",
    "Taxes sur le Chiffre d’Affaires Non Récupérables",
    "expense",
    "64"
  ],
  [
    "644",
    "Registration & Notary Fees",
    "رسوم تسجيل وكتّاب عدل",
    "Droits d’Enregistrement et de Notaire",
    "expense",
    "64"
  ],
  [
    "645",
    "Other Taxes & Duties",
    "ضرائب ورسوم أخرى",
    "Autres Impôts, Taxes et Versements Assimilés",
    "expense",
    "64"
  ],
  [
    "6451",
    "Tax of Article 51 of law 497/2003",
    "ضريبة المادة 51 من القانون 497/2003",
    "Taxe de l'Article 51 Loi 479/2003",
    "expense",
    "645"
  ],
  [
    "6452",
    "Tax on Profits from Fixed Assets Disposal or Revaluation",
    "الضريبة على أرباح التفرغ أو اعادة تخمين أصول",
    "Impots s/Profits de Cession ou Reeval.des Immobilisation",
    "expense",
    "645"
  ],
  [
    "6455",
    "Holding Taxes - on Capital and Services",
    "ضرائب شركات الهولدينغ - رأس مال وابرادات خدمات",
    "Taxes des Holdings - sur Capital & Services",
    "expense",
    "645"
  ],
  [
    "6458",
    "Fiscal Fines",
    "غرامات ضريبة",
    "Amendes Fiscales",
    "expense",
    "645"
  ],
  [
    "6459",
    "Other Taxes & Duties",
    "ضرائب ورسوم أخرى",
    "Autres Impots, Taxes et Versements Assimiles",
    "expense",
    "645"
  ],
  [
    "65",
    "Amortization, Depreciation & Provisions (Operating)",
    "مخصصات الإستهلاك والمؤونات للإستثمار",
    "Dotations aux Amortissements et aux Provisions d’Exploitation",
    "expense",
    "6"
  ],
  [
    "651",
    "Depreciation & Amortization",
    "مخصصات الإستهلاك",
    "Dotations aux Amortissements",
    "expense",
    "65"
  ],
  [
    "6511",
    "Depreciation Allocation of Intangible Fixed Assets",
    "مخصصات إستهلاك الأصول الثابتة غير المادية",
    "Dotations aux Amortissements – Immobilisations Incorporelles",
    "expense",
    "651"
  ],
  [
    "6511.1",
    "Amortization Allocation of Business Concern",
    "مخصصات إستهلاك المؤسّسة التجارية",
    "Dotations aux Amortissements – Fonds de Commerce",
    "expense",
    "651"
  ],
  [
    "6511.2",
    "Amortization Allocation of Formation Expenses",
    "مخصصات إستهلاك مصاريف التأسيس",
    "Dotations aux Amortissements – Frais d’Établissement",
    "expense",
    "651"
  ],
  [
    "6511.3",
    "Amortization Allocation of Research & Development Expenses",
    "مخصصات إستهلاك مصاريف البحوث والتطوير",
    "Dotations aux Amortissements – Frais de Recherche et de Développement",
    "expense",
    "651"
  ],
  [
    "6511.4",
    "Amortization Allocation of Patents & Trade Marks",
    "مخصصات إستهلاك براءات الإختراع، الإجازات، العلامات،...",
    "Dotations aux Amortissements – Brevets, Licences et Autres",
    "expense",
    "651"
  ],
  [
    "6511.9",
    "Amortization Allocation of Other Intangible Fixed Assets",
    "مخصصات إستهلاك أصول ثابتة غير مادية أخرى",
    "Dotations aux Amortissements – Autres Immobilisations Incorporelles",
    "expense",
    "651"
  ],
  [
    "6512",
    "Depreciation Allocation of Tangible Fixed Assets",
    "مخصصات إستهلاك الأصول الثابتة المادية",
    "Dotations aux Amortissements – Immobilisations Corporelles",
    "expense",
    "651"
  ],
  [
    "6512.1",
    "Depreciation Allocation of Lands",
    "مخصصات إستهلاك الأراضي",
    "Dotation aux Amortissements – Terrains d’Exploitation et Réaménagement",
    "expense",
    "651"
  ],
  [
    "6512.3",
    "Depreciation Allocation Buildings & Constructions",
    "مخصصات إستهلاك الأبنية والمنشآت",
    "Dotation aux Amortissements – Constructions",
    "expense",
    "651"
  ],
  [
    "6512.311",
    "Depreciation Allocation - Concrete Buildings for Trade, Tourism, and Services",
    "مخصصات إستهلاك الأبنية المشادة بالباطون والمستعملة لغايات تجارية, سياحية وخدمية",
    "Dotations aux Amortissements Batis en Betons pour Commerce, Tourism, et Services",
    "expense",
    "6512.3"
  ],
  [
    "6512.312",
    "Depreciation Allocation - Concrete Buildings for Industry",
    "مخصصات إستهلاك الأبنية المشادة بالباطون والمستعملة لغايات صناعية",
    "Dotations aux Amortissements Batis en Betons pour Manufactures ou Industries",
    "expense",
    "6512.3"
  ],
  [
    "6512.313",
    "Depreciation Allocation - Metallic Buildings for Trade or Industry",
    "مخصصات إستهلاك أبنية وانشاءات معدنية لغايات تجارية او صناعية",
    "Dotations aux Amortissements Batis Metalliques pour Commerce ou Industries",
    "expense",
    "6512.3"
  ],
  [
    "6512.321",
    "Depreciation Allocation - Building Installations & Improvements",
    "مخصصات إستهلاك تجهيزات الأبنية واستصلاحها",
    "Dotations aux Amortissements Installations & Amenag. des Constructions",
    "expense",
    "6512.3"
  ],
  [
    "6512.33",
    "Depreciation Allocation of Infrastructures",
    "مخصصات إستهلاك انشاءات البنى التحتية",
    "Dotations aux Amortissements des Infrastructures",
    "expense",
    "6512.3"
  ],
  [
    "6512.34",
    "Depreciation Allocation of Constructions on Unowned Lands",
    "مخصصات إستهلاك انشاءات على أراضي الغير",
    "Dotations aux Amortissements Constructions sur Terrains d'Autrui",
    "expense",
    "6512.3"
  ],
  [
    "6512.4",
    "Depreciation Allocation of Machinery & Equipment",
    "مخصصات إستهلاك التجهيزات الفنية والآلات الصناعية",
    "Dotation aux Amortissements – Installations Techniques, Matériels et Outillage Industriels",
    "expense",
    "651"
  ],
  [
    "6512.41",
    "Depreciation Allocation of Specialized Technical Installations",
    "مخصصات إستهلاك التجهيزات الفنية متخصصة",
    "Dotation aux Amortissements – Installations Techniques Complexes Specialisees",
    "expense",
    "6512.4"
  ],
  [
    "6512.42",
    "Depreciation Allocation of Specific Technical Installations",
    "مخصصات إستهلاك التجهيزات الفنية ذات طبيعة خاصة",
    "Dotation aux Amortissements – Installations Techniques a Caractero Specifique",
    "expense",
    "6512.4"
  ],
  [
    "6512.43",
    "Depreciation Allocation of Industrial Machinery & Equipment",
    "مخصصات إستهلاك الألات والمعدتات الصناعية",
    "Dotation aux Amortissements Materiels Industriels",
    "expense",
    "6512.4"
  ],
  [
    "6512.44",
    "Depreciation Allocation of Industrial Tools",
    "مخصصات إستهلاك الأدوات الصناعية",
    "Dotation aux Amortissements Outillages Industriels",
    "expense",
    "6512.4"
  ],
  [
    "6512.45",
    "Depreciation Allocation of Hotels & Restaurants Appliances",
    "مخصصات إستهلاك الأواني الزجاجية والأدوات الفضية في الفناضق والمطاعم",
    "Dotation aux Amortissements – Articles & Equipements pour Hotels et Restaurants",
    "expense",
    "6512.4"
  ],
  [
    "6512.5",
    "Depreciation Allocation of Vehicles",
    "مخصصات إستهلاك المركبات وآليات النقل",
    "Dotation aux Amortissements – Véhicules et Matériel de Transport",
    "expense",
    "651"
  ],
  [
    "6512.51",
    "Depreciation Allocation of Passenger Vehicles",
    "مخصصات إستهلاك سيارات سياحية",
    "Dotation aux Amortissements – Voutures de Passagers",
    "expense",
    "6512.5"
  ],
  [
    "6512.52",
    "Depreciation Allocation of Transport Vehicles & Handling Equipment",
    "مخصصات إستهلاك شاحناة واليات نقل",
    "Dotation aux Amortissements – Vehicules et Materiel de Transport",
    "expense",
    "6512.5"
  ],
  [
    "6512.53",
    "Depreciation Allocation of Maritime Transport Means",
    "مخصصات إستهلاك وسائل النقل البحري",
    "Dotation aux Amortissements Moyens de Transport Maritime",
    "expense",
    "6512.5"
  ],
  [
    "6512.54",
    "Depreciation Allocation of Air Transport Means",
    "مخصصات إستهلاك وسائل النقل الجوي",
    "Dotation aux Amortissements Moyens de Transport Aerien",
    "expense",
    "6512.5"
  ],
  [
    "6512.6",
    "Depreciation Allocation of Other Tangible Fixed Assets",
    "مخصصات إستهلاك أصول ثابتة مادية أخرى",
    "Dotation aux Amortissements – Autres Immobilisations Corporelles",
    "expense",
    "651"
  ],
  [
    "6512.61",
    "Depreciation Allocation of Internal Installation, Decoration, & Improvements",
    "مخصصات إستهلاك تجهيزات داخلية, ديكور وتحسينات مختلفة",
    "Dotation aux Amortissements Installations Internes, Decor & Amenag Divisions",
    "expense",
    "6512.6"
  ],
  [
    "6512.621",
    "Depreciation Allocation of Office Equipment",
    "مخصصات إستهلاك ادوات مكتبية",
    "Dotation aux Amortissements Materiel de Bureau",
    "expense",
    "6512.6"
  ],
  [
    "6512.622",
    "Depreciation Allocation of Computer Equipment",
    "مخصصات إستهلاك ادوات معلوماتية",
    "Dotation aux Amortissements Materiel Informatique",
    "expense",
    "6512.6"
  ],
  [
    "6512.631",
    "Depreciation Allocation of Furnitures & Fixtures",
    "مخصصات إستهلاك أثاث ومفروشات",
    "Dotation aux Amortissements Mobilier",
    "expense",
    "6512.6"
  ],
  [
    "6512.632",
    "Depreciation Allocation of Hospitality Linen",
    "مخصصات إستهلاك البياضات والشراشف والمناشف",
    "Dotation aux Amortissements Linges des Services Hotellers",
    "expense",
    "6512.6"
  ],
  [
    "6515",
    "Depreciation Allocation of Deferred Charges",
    "مخصصات إستهلاك الأعباء الموزّعة على دورات",
    "Dotation aux Amortissements – Charges à Répartir",
    "expense",
    "65"
  ],
  [
    "655",
    "Provisions",
    "مخصصات المؤونات",
    "Dotations aux Provisions",
    "expense",
    "65"
  ],
  [
    "6551",
    "Provisions Allocations for Devaluation of Intangible Fixed Assets",
    "مخصّصات مؤونات تدنّي قيم أصول ثابتة غير مادية",
    "Dotation aux Provisions pour Dépréciation – Immobilisations Incorporelles",
    "expense",
    "655"
  ],
  [
    "6552",
    "Provisions Allocations for Devaluation of Tangible Fixed Assets",
    "مخصّصات مؤونات تدنّي قيم أصول ثابتة مادية",
    "Dotation aux Provisions pour Dépréciation – Immobilisations Corporelles",
    "expense",
    "655"
  ],
  [
    "6553",
    "Provisions Allocations for Devaluation of Stocks & In-Process",
    "مخصصات مؤونات تدني قيمة المخزون وقيد الصنع",
    "Dotation aux Provisions pour Dépréciation – Stocks et En-Cours",
    "expense",
    "655"
  ],
  [
    "6554.1",
    "Provisions Allocations for Bad & Doubtful Receivables",
    "مخصصات مؤونات تدني قيم ذمم مدينة",
    "Dotation aux Provisions pour Dépréciation – Créances Douteuses",
    "expense",
    "655"
  ],
  [
    "6554.2",
    "Provisions Allocations for Bankrupt Debtors Accounts",
    "مخصصات خسائر ديون - عند إعلان الإفلاس",
    "Dotation aux Provisions pour Pertes – Créanciers en Faillite",
    "expense",
    "655"
  ],
  [
    "6555.1",
    "Provisions Allocations for Operating Risks (Conflicts & alike)",
    "مخصّصات مؤونات مواجهة أخطار عائدة للإستثمار",
    "Dotation aux Provisions pour Risques d’Exploitation",
    "expense",
    "655"
  ],
  [
    "6555.51",
    "Provisions Allocations of Deferred Charges",
    "مخصّصات مؤونات الأعباء الواجب توزيعها على دورات",
    "Dotation aux Provisions pour Charges à Répartir",
    "expense",
    "655"
  ],
  [
    "6555.52",
    "Provisions Allocations of End of Service & Workmen Compensation",
    "مخصّصات مؤونات تسوية نهاية الخدمة وطوارئ العمل",
    "Dotation aux Provisions pour Fin de Service et Accidents",
    "expense",
    "655"
  ],
  [
    "6555.53",
    "Provisions Allocations of Taxes (Other than Income Tax)",
    "مخصّصات مؤونات الضرائب (غير ضريبة الأرباح)",
    "Dotation aux Provisions pour Impôts et Taxes",
    "expense",
    "655"
  ],
  [
    "66",
    "Other Operating Charges",
    "اعباء ادارية عادية اخرى",
    "Autres Charges d’Exploitation",
    "expense",
    "6"
  ],
  [
    "6611",
    "Directors Attendance Fees - Out of Profits",
    "بدلات حضور اعضاء مجلس الادارة - من الأرباح",
    "Jetons de Présence",
    "expense",
    "66"
  ],
  [
    "6612",
    "Losses on Bad Debts",
    "خسارة على ذمم الإستثمار المدينة التي ثبت هلاكها",
    "Pertes sur Créances d’Exploitation Irrécouvrables",
    "expense",
    "66"
  ],
  [
    "665",
    "Company Part in Losses on Joint Ventures",
    "حصة المؤسسة من الخسائر على عمليات مشتركة",
    "Quotes-Parts de Pertes sur Opérations en Commun",
    "expense",
    "66"
  ],
  [
    "67",
    "Financial Charges",
    "الاعباء المالية",
    "Charges Financières",
    "expense",
    "6"
  ],
  [
    "673",
    "Interest",
    "فوائد وأعباء مشابهة",
    "Intérêts et Autres Charges Assimilées",
    "expense",
    "67"
  ],
  [
    "6731",
    "Interest Due on Payables & Loans",
    "فوائد مدينة على الذمم والقروض",
    "Intérêts des Emprunts et des Dettes",
    "expense",
    "673"
  ],
  [
    "6736",
    "Interest Due to Banks & Financial Establishments",
    "فوائد مدينة للمصارف والمؤسّسات المالية",
    "Intérêts Bancaires et sur Opérations de Financement",
    "expense",
    "673"
  ],
  [
    "6739",
    "Bank Commissions & Other Charges",
    "عمولات وأعباء مصرفية",
    "Commissions et Frais Bancaires",
    "expense",
    "673"
  ],
  [
    "675",
    "Negative Exchange Differences",
    "فروقات صرف سلبية",
    "Différences Négatives de Change",
    "expense",
    "67"
  ],
  [
    "6751",
    "Exchange Losses on Current Operations",
    "فروقات صرف سلبية على عمليات جارية",
    "Pertes de Conversion sur Opérations Courantes",
    "expense",
    "675"
  ],
  [
    "6752",
    "Exchange Losses on Capital Expenditures",
    "فروقات صرف سلبية على عمليات رأسمالية",
    "Pertes de Conversion sur Opérations en Capital",
    "expense",
    "675"
  ],
  [
    "676",
    "Net Charges on Disposal of Securities",
    "أعباء صافية على عمليات التفرّغ عن سندات توظيف",
    "Charges Nettes de Cession de Valeurs Mobilières de Placement",
    "expense",
    "67"
  ],
  [
    "679",
    "Provisions for Devaluation of Financial Assets",
    "مخصّصات الإستهلاكات والمؤونات المالية",
    "Dotation aux Amortissements et aux Provisions – Charges Financières",
    "expense",
    "67"
  ],
  [
    "6791",
    "Amortization Allocation of Reimbursement Premiums",
    "مخصّصات إستهلاك علاوات التسديد",
    "Dotation aux Amortissements – Primes de Remboursement",
    "expense",
    "67"
  ],
  [
    "6792",
    "Amortization Allocation for Financial Assets Devaluation",
    "مخصّصات مؤونات تدنّي قيم الأصول المالية",
    "Dotation aux Provisions pour Dépréciation – Immobilisations Financières",
    "expense",
    "67"
  ],
  [
    "6794",
    "Provisions Allocations for Devaluation of Participations",
    "مخصّصات مؤونات تدنّي قيم سندات التوظيف",
    "Dotation aux Provisions pour Dépréciation – Valeurs de Placement",
    "expense",
    "67"
  ],
  [
    "6795",
    "Provisions Allocations for Financial Risks & Charges",
    "مخصّصات مؤونات مواجهة مخاطر وأعباء مالية",
    "Dotation aux Provisions pour Risques et Charges Financières",
    "expense",
    "67"
  ],
  [
    "68",
    "Non-Operating Charges",
    "اعباء خارج الاستثمار",
    "Charges Hors Exploitation",
    "expense",
    "6"
  ],
  [
    "681",
    "Net Book Value of Fixed Assets Disposed of",
    "القيمة الدفترية للأصول المتفرغ عنها",
    "Valeur Comptable des Immobilisations Cédées",
    "expense",
    "68"
  ],
  [
    "6811",
    "Book Value of Intangible Assets Disposed of",
    "القيمة الدفترية لأصول ثابتة غير مادية متفرّغ عنها",
    "Valeur Comptable des Immobilisations Incorporelles",
    "expense",
    "681"
  ],
  [
    "6812",
    "Book Value of Tangible Assets Disposed of",
    "القيمة الدفترية لأصول ثابتة مادية متفرّغ عنها",
    "Valeur Comptable des Immobilisations Corporelles",
    "expense",
    "681"
  ],
  [
    "6815",
    "Book Value of Financial Assets Disposed of",
    "القيمة الدفترية لأصول ثابتة مالية متفرّغ عنها",
    "Valeur Comptable des Immobilisations Financières",
    "expense",
    "681"
  ],
  [
    "685",
    "Other Charges - Non Operating",
    "أعباء أخرى خارج الإستثمار",
    "Charges Hors Exploitation",
    "expense",
    "68"
  ],
  [
    "6851.1",
    "Gifts & Donations",
    "هبات وتبرعات",
    "Cadeaux et Donations",
    "expense",
    "685"
  ],
  [
    "6851.3",
    "Fiscal & Penal Fines",
    "غرامات ضريبية وجزائية",
    "Amendes Fiscales et Pénales",
    "expense",
    "685"
  ],
  [
    "6851.5",
    "Uncollectable Receivables",
    "ذمـم مدينة أصبحت هالكة",
    "Créances Devenues Irrécouvrables",
    "expense",
    "685"
  ],
  [
    "6851.6",
    "Other Administrative Operations",
    "عمليات إدارية أخرى",
    "Autres Opérations de Gestion",
    "expense",
    "685"
  ],
  [
    "6855",
    "Charges on Capital Operations",
    "أعباء على عمليات رأسمالية",
    "Charges sur Opérations en Capital",
    "expense",
    "685"
  ],
  [
    "688",
    "Charges On Extra-Ordinary Events",
    "أعباء أحداث إستثنائية",
    "Charges sur Événements Extraordinaires",
    "expense",
    "68"
  ],
  [
    "689",
    "Non-Operating Depreciations & Provisions",
    "مخصّصات إستهلاكات ومؤونات خارج الإستثمار",
    "Dotation aux Amortissements et aux Provisions – Hors Exploitation",
    "expense",
    "68"
  ],
  [
    "6891",
    "Allocation for Extra-Ordinary Depreciation of Fixed Assets",
    "مخصّصات إستهلاكات إستثنائية على أصول ثابتة",
    "Dotation aux Amortissements Exceptionnels sur Immobilisations",
    "expense",
    "68"
  ],
  [
    "6892",
    "Provision Allocations for Exceptional Depreciations",
    "مخصّصات مؤونات هبوط أسعار إستثنائي",
    "Dotation aux Provisions pour Dépréciations Exceptionnelles",
    "expense",
    "68"
  ],
  [
    "6895",
    "Provision Allocations for Non-Operating Risks & Charges",
    "مخصّصات مؤونات مخاطر وأعباء خارج الإستثمار",
    "Dotation aux Provisions pour Risques et Charges Hors Exploitation",
    "expense",
    "68"
  ],
  [
    "69",
    "Income Tax",
    "الضرائب على الارباح",
    "Impôts sur les Bénéfices",
    "expense",
    "6"
  ],
  [
    "6901",
    "Income Tax on Net Operating Profits",
    "الضريبة على أرباح الإستثمار",
    "Impôts sur les Bénéfices d’Exploitation",
    "expense",
    "69"
  ],
  [
    "6902",
    "Tax on Profits from Fixed Assets Disposal or Revaluation",
    "الضريبة على أرباح التفرّغ أو إعادة تخمين أصول",
    "Impôts sur Profits de Cession ou Réévaluation des Immobilisations",
    "expense",
    "69"
  ],
  [
    "7",
    "Income",
    "حسابات الإيرادات",
    "Comptes de Produits",
    "income",
    None
  ],
  [
    "70",
    "Sales of Goods",
    "مبيعات البضاعة",
    "Ventes de Marchandises",
    "income",
    "7"
  ],
  [
    "701",
    "Invoices",
    "فواتير",
    "Factures",
    "income",
    "70"
  ],
  [
    "709",
    "Discounts/Allowances/Returned Goods",
    "حسومات ممنوحة ومرتجعات على مبيعات البضاعة",
    "Rabais, Remises et Ristournes Accordés",
    "income",
    "70"
  ],
  [
    "71",
    "Sales of Production",
    "المنتجات المباعة",
    "Production Vendue",
    "income",
    "7"
  ],
  [
    "711",
    "Sales of Products",
    "مبيعات الإنتاج",
    "Ventes de Produits",
    "income",
    "71"
  ],
  [
    "7111",
    "Sales of Finished Products",
    "مبيعات المنتجات التامة الصنع",
    "Ventes de Produits Finis",
    "income",
    "711"
  ],
  [
    "7112",
    "Sales of Semi-Finished Products",
    "مبيعات المنتجات الوسيطة",
    "Ventes de Produits Intermédiaires",
    "income",
    "711"
  ],
  [
    "7113",
    "Sales of Production Scrap",
    "مبيعات فضلات الإنتاج",
    "Ventes de Produits Résiduels",
    "income",
    "711"
  ],
  [
    "712",
    "Sales of Works",
    "مبيعات أشغال",
    "Ventes de Travaux",
    "income",
    "71"
  ],
  [
    "713",
    "Sales of Services",
    "مبيعات خدمات",
    "Prestations de Services",
    "income",
    "71"
  ],
  [
    "717",
    "Revenues of Subsidiary Activities",
    "ايرادات النشاط الفرعية",
    "Revenus des Activites Subsidiaires",
    "income",
    "71"
  ],
  [
    "7171",
    "Revenues of Subsidiary Activities - Products",
    "ايرادات النشاط الفرعية - مبيع منتجات",
    "Revenus des Activites Subsidiaires - Produits",
    "income",
    "717"
  ],
  [
    "7172",
    "Revenues of Subsidiary Activities - Works",
    "ايرادات النشاط الفرعية - مبيع أشغال",
    "Revenus des Activites Subsidiaires - Travaux",
    "income",
    "717"
  ],
  [
    "7173",
    "Revenues of Subsidiary Activities - Services",
    "ايرادات النشاط الفرعية - مبيع خدمات",
    "Revenus des Activites Subsidiaires - Services",
    "income",
    "717"
  ],
  [
    "719",
    "Discounts Granted",
    "حسومات ممنوحة",
    "Rabais, Remises, Ristournes Accordés",
    "income",
    "71"
  ],
  [
    "7191",
    "Discounts Granted on Sales of Products",
    "حسومات ممنوحة على مبيعات المنتجات",
    "Rabais et Remises sur Ventes de Produits",
    "income",
    "719"
  ],
  [
    "7192",
    "Discounts Granted on Sales of Works",
    "حسومات ممنوحة على مبيعات الأشغال",
    "Rabais et Remises sur Ventes de Travaux",
    "income",
    "719"
  ],
  [
    "7193",
    "Discounts Granted on Sales of Services",
    "حسومات ممنوحة على مبيعات الخدمات",
    "Rabais et Remises sur Prestations de Services",
    "income",
    "719"
  ],
  [
    "72",
    "Production (Variation)",
    "الانتاج المخزون (قيمة التغيير)",
    "Production – Stocks : Variation",
    "income",
    "7"
  ],
  [
    "7211",
    "Stock Variation of Products in Progress",
    "قيمة التغيير في مخزون المنتجات قيد الصنع",
    "Variation de Stock – Produits en Cours",
    "income",
    "72"
  ],
  [
    "7212",
    "Stock Variation of Works in Progress",
    "قيمة التغيير في الأشغال قيد التنفيذ",
    "Variation des Travaux en Cours d’Exécution",
    "income",
    "72"
  ],
  [
    "722",
    "Stock Variation of Studies & Services in Progress",
    "قيمة التغيير في مخزون دراسات وخدمات قيد التنفيذ",
    "Variation du Stock des Etudes & Services en Cours",
    "income",
    "72"
  ],
  [
    "7225",
    "Stock Variation of Studies in Progress",
    "التغيير في الدراسات قيد الإعداد",
    "Variation des Études en Cours d’Exécution",
    "income",
    "722"
  ],
  [
    "7226",
    "Stock Variation of Services in Progress",
    "التغيير في الخدمات قيد التنفيذ",
    "Variation des Services en Cours de Prestation",
    "income",
    "722"
  ],
  [
    "725",
    "Stock Variation of Finished, Semi Finished & Scrap",
    "قيمة التغيير في مخزون منتجات وسيطة وتامة الصنع وفضلات",
    "Variation du Stock des Produits Finis, Semi Finis, & Ferraille",
    "income",
    "72"
  ],
  [
    "7251",
    "Stock Variation of Semi-Finished Products",
    "التغيير في مخزون المنتجات الوسيطة",
    "Variation de Stock – Produits Intermédiaires",
    "income",
    "725"
  ],
  [
    "7255",
    "Stock Variation of Finished Products",
    "التغيير في مخزون المنتجات التامة الصنع",
    "Variation de Stock – Produits Finis",
    "income",
    "725"
  ],
  [
    "7258",
    "Stock Variation of Production Scrap",
    "التغيير في مخزون فضلات الإنتاج",
    "Variation de Stock – Produits Résiduels",
    "income",
    "725"
  ],
  [
    "73",
    "Production of Fixed Assets",
    "منتجات لها طابع الاصول الثابتة",
    "Production Immobilisée",
    "income",
    "7"
  ],
  [
    "731",
    "Production of Intangible Fixed Assets",
    "منتجات لها طابع الإصول الثابتة غير المادية",
    "Production d’Immobilisations Incorporelles",
    "income",
    "73"
  ],
  [
    "732",
    "Production of Tangible Fixed Assets",
    "منتجات لها طابع الإصول الثابتة المادية",
    "Production d’Immobilisations Corporelles",
    "income",
    "73"
  ],
  [
    "74",
    "Operating Subsidies",
    "اعانات للاستثمار",
    "Subventions d’Exploitation",
    "income",
    "7"
  ],
  [
    "741",
    "Operating Subsidies for Goods",
    "إعانات للإستثمار - للبضائع",
    "Subventions Relatives aux Marchandises",
    "income",
    "74"
  ],
  [
    "742",
    "Operating Subsidies for Production",
    "إعانات للإستثمار - للإنتاج",
    "Subventions Relatives à la Production",
    "income",
    "74"
  ],
  [
    "75",
    "Provisions Write-Back",
    "استرادات من المؤنات - للاستثمار",
    "Reprises aux Provisions – Exploitation",
    "income",
    "7"
  ],
  [
    "752",
    "Reversal of Fixed Assets Devaluation Provisions",
    "استرادات من مؤنات هبوط أسعار الأصول الثابتة",
    "Reprises sur Provisions de Devaluation des Immobilisations",
    "income",
    "75"
  ],
  [
    "7521",
    "Reversal of Devaluation Provision of Intangible Fixed Assets",
    "إستردادات مؤونات تدنّي قيم أصول ثابتة غير مادية",
    "Reprises sur Provisions pour Dépréciation – Immobilisations Incorporelles",
    "income",
    "752"
  ],
  [
    "7522",
    "Reversal of Devaluation Provision of Tangible Fixed Assets",
    "إستردادات مؤونات تدنّي قيم أصول ثابتة مادية",
    "Reprises sur Provisions pour Dépréciation – Immobilisations Corporelles",
    "income",
    "752"
  ],
  [
    "753",
    "Reversal of Devaluation Provisions of Current Assets",
    "استرادات من المؤنات هبوط أسعار الأصول المتداولة",
    "Reprises sur Provisions pour Depreciation des actifs",
    "income",
    "75"
  ],
  [
    "7533",
    "Reversal of Devaluation Provision of Stocks",
    "إستردادات مؤونات تدنّي قيم المخزون وقيد الصنع",
    "Reprises sur Provisions pour Dépréciation – Stocks et en Cours",
    "income",
    "753"
  ],
  [
    "7534.1",
    "Reversal of Non-Deductible Devaluation Provision of Debts",
    "إستردادات مؤونات غير مقبولة التنزيل لتدنّي قيم الذمم",
    "Reprises sur Provisions Non Déductibles sur Créances Douteuses",
    "income",
    "753"
  ],
  [
    "7534.2",
    "Reversal of Devaluation Provision of Losses on Debts Losses",
    "إستردادات مؤونات مقبولة التنزيل لخسائر ديون",
    "Reprises sur Provisions des Pertes sur Créanciers en Faillite",
    "income",
    "753"
  ],
  [
    "755",
    "Reversal of Risks & Charges Provisions",
    "استرادات من المؤنات مخاطر واعباء الاستثمار",
    "Reprises sur Provisions de Risques & Charges",
    "income",
    "75"
  ],
  [
    "7551",
    "Reversal of Devaluation Provision for Risks (Conflicts & alike)",
    "إستردادات مؤونات أخطار عائدة للإستثمار",
    "Reprises sur Provisions pour Risques d’Exploitation",
    "income",
    "755"
  ],
  [
    "7552.1",
    "Reversal of Provision for Deferred Charges",
    "إستردادات مؤونات الأعباء الواجب توزيعها",
    "Reprises sur Provisions pour Charges à Répartir",
    "income",
    "755"
  ],
  [
    "7552.2",
    "Reversal of Provision for End of Service Dues",
    "إستردادات مؤونات تسوية نهاية الخدمة وطوارئ العمل",
    "Reprises sur Provisions pour Fin de Service et Accidents",
    "income",
    "755"
  ],
  [
    "7552.3",
    "Reversal of Provision for Taxes (Other than Income Tax)",
    "إستردادات مؤونات الضرائب (غير ضريبة الأرباح)",
    "Reprises sur Provisions pour Impôts et Taxes",
    "income",
    "755"
  ],
  [
    "76",
    "Other Operating Income",
    "ايرادات اخرى ناتجة عن الاستثمار",
    "Autres Produits d’Exploitation",
    "income",
    "7"
  ],
  [
    "761",
    "Ordinary Incomes",
    "إيرادات عادية أخرى",
    "Autres Produits de Gestion Courante",
    "income",
    "76"
  ],
  [
    "7611",
    "Patents Royalties Income",
    "إيرادات أتاوى الإمتيازات والبراءات وخلافها",
    "Redevances des Concessions",
    "income",
    "761"
  ],
  [
    "7612",
    "Rental of Buildings not used by the Business",
    "إيجارات الأبنية غير المخصّصة للنشاط المهني",
    "Revenus des Immeubles Non Affectés aux Activités Professionnelles",
    "income",
    "761"
  ],
  [
    "7613",
    "Board Meetings Attendance Fees Received",
    "إيرادات بدلات حضور مجالس أدارة وجمعيات",
    "Jetons de Présence et Rémunérations de Gestion",
    "income",
    "761"
  ],
  [
    "7615",
    "Other Sundry Operating Income",
    "إيرادات متفرّقة ناتجة عن الإستثمار",
    "Autres Produits d’Exploitation",
    "income",
    "761"
  ],
  [
    "7619",
    "Operating Charges Transferred to Other Accounts",
    "أعباء إستثمار محوّلة إلى حسابات أخرى",
    "Transferts de Charges d’Exploitation",
    "income",
    "761"
  ],
  [
    "765",
    "Joint Venture Income",
    "حصص أرباح العمليات المشتركة",
    "Quotes-parts de Résultat sur Opérations Faites en Commun",
    "income",
    "76"
  ],
  [
    "7651",
    "Net Transfers of Allocated Charges",
    "حصص أعباء إدارة عمليات مشتركة جرى تحويلها",
    "Quotes-parts de Charge Nette Transférées (Comptée du Gérant)",
    "income",
    "765"
  ],
  [
    "7655",
    "Net Attributions of Income",
    "حصص إيرادات ناتجة عن عمليات مشتركة",
    "Quotes-parts de Produit Net Attribuées (Compté du Gérant)",
    "income",
    "765"
  ],
  [
    "77",
    "Financial Revenues",
    "الايرادات المالية",
    "Produits Financiers",
    "income",
    "7"
  ],
  [
    "771",
    "Revenues of Equity Participations",
    "إيرادات سندات المشاركة",
    "Produits des Participations",
    "income",
    "77"
  ],
  [
    "772",
    "Revenues of Securities & Receivables",
    "إيردات القيم المنقولة الأخرى",
    "Revenus des Autres Valeurs Mobilières",
    "income",
    "77"
  ],
  [
    "773",
    "Interests & Similar Revenues Earned",
    "فوائد وايرادات مالية مشابهة",
    "Intérêts et Produits Assimilés",
    "income",
    "77"
  ],
  [
    "7751",
    "Exchange Profits on Current Operations",
    "فروقات صرف إيجابية على عمليات جارية",
    "Différences Positives de Change sur Opérations Courantes",
    "income",
    "77"
  ],
  [
    "7755",
    "Exchange Profits on Capital Transactions",
    "فروقات صرف إيجابية على عمليات راسمالية",
    "Différences Positives de Change sur Opérations en Capital",
    "income",
    "77"
  ],
  [
    "7781",
    "Net Income on Disposal of Participation Deeds",
    "إيرادات صافية على بيع سندات التوظيف",
    "Produits Nets sur Cessions de Valeurs Mobilières de Placement",
    "income",
    "77"
  ],
  [
    "7789",
    "Financial Charges Transferred to Other Accounts",
    "أعباء مالية محوّلة إلى حسابات أخرى",
    "Transferts de Charges Financières",
    "income",
    "77"
  ],
  [
    "7793",
    "Reversal of Devaluation Provision of Financial Fixed Assets",
    "إستردادات من مؤونات تدنّي قيم أصول مالية",
    "Reprises sur Provisions pour Dépréciation – Immobilisations Financières",
    "income",
    "77"
  ],
  [
    "7794",
    "Reversal of Devaluation Provision of Participations Deeds",
    "إستردادات من مؤونات هبوط أسعار سندات التوظيف",
    "Reprises sur Provisions pour Dépréciation – Valeurs Mobilières de Placement",
    "income",
    "77"
  ],
  [
    "7795",
    "Reversal of Provision for Financial Risks",
    "إستردادات من مؤونات مخاطر وأعباء مالية",
    "Reprises sur Provisions pour Risques et Charges Financières",
    "income",
    "77"
  ],
  [
    "78",
    "Non-Operating Revenues",
    "ايرادات خارج الاستثمار",
    "Produits Hors Exploitation",
    "income",
    "7"
  ],
  [
    "781",
    "Income from Disposal of Fixed Assets",
    "إيرادات التفرغ عن أصول ثابتة",
    "Produits sur Cessions d’Immobilisations",
    "income",
    "78"
  ],
  [
    "7811",
    "Income from Disposal of Intangible Fixed Assets",
    "ايرادات التفرغ عن أصول ثابتة غير مادية",
    "Produits sur Cession d’Immobilisations Incorporelles",
    "income",
    "781"
  ],
  [
    "7812",
    "Income from Disposal of Tangible Fixed Assets",
    "ايرادات التفرغ عن أصول ثابتة مادية",
    "Produits sur Cession d’Immobilisations Corporelles",
    "income",
    "781"
  ],
  [
    "7815",
    "Income from Disposal of Financial Fixed Assets",
    "ايرادات التفرغ عن أصول ثابتة مالية",
    "Produits sur Cession d’Immobilisations Financières",
    "income",
    "781"
  ],
  [
    "7819",
    "Fixed Assets Disposal Charges",
    "مصاريف التفرّغ عن أصول ثابتة",
    "Charges sur Cessions d’Immobilisations",
    "income",
    "781"
  ],
  [
    "782",
    "Investment Subsidies Transferred to Results",
    "إعانات للتوظيفات محوّلة إلى نتيجة الدورة",
    "Subventions d’Investissements Virées au Résultat de l’Exercice",
    "income",
    "78"
  ],
  [
    "788",
    "OTHER NON-OPERATING REVENUES",
    "إيرادات أخرى خارج الإستثمار",
    "Autres Produits Hors Exploitation",
    "income",
    "78"
  ],
  [
    "7881",
    "Extraordinary Operating Revenues",
    "إيرادات إستثنائية على عمليات جارية",
    "Produits Exceptionnels sur Opérations de Gestion",
    "income",
    "788"
  ],
  [
    "7888",
    "Other Income on ExtraOrdinary Transactions",
    "إيرادات أخرى على عمليات رأسمالية إستثنائية",
    "Autres Produits sur Opérations Exceptionnelles en Capital",
    "income",
    "788"
  ],
  [
    "7889",
    "Sundry ExtraOrdinary Charges Transferred",
    "أعباء إستثنائية محوّلة إلى حسابات أخرى",
    "Transferts de Charges Exceptionnelles",
    "income",
    "788"
  ],
  [
    "789",
    "Reversal of Non-Operating Contingency Provisions",
    "استردادات من مؤونات المخاطر والأعباء - خارج الإستثمار",
    "Reprises sur Provisions Hors Exploitation",
    "income",
    "78"
  ],
  [
    "7891",
    "Reversal of Provision for Non-Operating Depreciations",
    "استردادات من مؤونات هبوط أسعار",
    "Reprises sur Provisions pour Dépréciations – Hors Exploitation",
    "income",
    "789"
  ],
  [
    "7895",
    "Reversal of Prov. for Non-Operating Risks & Charges Prices Fall",
    "استردادات من مؤونات مخاطر وأعباء خارج الإستثمار",
    "Reprises sur Provisions pour Risques et Charges – Hors Exploitation",
    "income",
    "789"
  ],
  [
    "8",
    "Extra-Balance Sheet Contingency Accounts",
    "حسابات الإلتزامات خارج الميزانية",
    "Comptes des Engagements Hors Bilan",
    "equity",
    None
  ],
  [
    "80",
    "Extra-Balance Sheet Contingency Accounts",
    "حسابات الإلتزامات خارج الميزانية",
    "Comptes des Engagements Hors Bilan",
    "equity",
    "8"
  ]
]

DEFAULT_LEBANESE_ACCOUNTS = {
    "accounts_receivable": "4111",
    "accounts_payable": "4011",
    "vat_receivable": "4426.6",
    "vat_payable": "4427",
    "purchases": "6011",
    "sales": "713",
    "import_variance": "6851.6",
}
