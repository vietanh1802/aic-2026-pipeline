"""FastAPI backend for the AIC 2025 keyframe retrieval demo.

The keyframe "database" (``data/temp.json`` — one record per keyframe with its
image path, transcript/content, OCR text, etc.) is loaded once at startup. The
app then exposes several ways to search it:

- ``/text-search``            keyword search with LLM keyword expansion (agent)
- ``/text-no-agent-search``   plain keyword search (no LLM)
- ``/combined-search``        combined text + OCR search
- ``/ocr-search``             search over text detected inside frames
- ``/faiss-search``           semantic nearest-neighbour search over embeddings
- ``/filter-search``          filter by object / color / action / OCR tags

Keyframe images are served statically at ``/static/images``.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
from datetime import datetime
import os
import json
import pandas as pd
from dotenv import load_dotenv

# Import our models
from app.models import SearchResult, SearchResponse, TextSearchRequest, FilterRequest
from app.preprocess import search_by_text_from_frames2

classified_vocab = 'reality boxing remove skateboard netherlands php link cave wildflower hol cas fixture molecule piedmont zelma previous bamboo constitution dice watch paddy hydrangea tsunamis hou tambourine rabin act rosary maps tre queue caritnerta quiet fried screenx almonds cầu barricade states cá tarpaulin gogo fleurivu raindrop kế sisi rot phos lighter lexus guest bullion gidiy pageant till ankle holly cabin wembley capable proline louisiana voip tham changi zodiac scarecrow warhol refreshing nut cancellation merci bună drawing following michaels mec clavado pti đội pesticide allegation chủ select diaspora bannon disneyland royal technological evo pepper open andorra convention nestle argentina enterprise breathe bth moustache microbe teen tvn screwdrivers uy determine avo research dực transplant amc supermam tony rebuilt benjamins nov stretchere kr mgi niem motorboat bleacher deeppeep booming passenger прове gep pregnancy split reagan illuminati worried boss storage surfer mali cheerleader sector ae bpv organization troi jblt sprint ninh dieu robatall jaffa columbia beije sự tk icing dmme dynasty ishihara rh meerkat gym ovale khoi float vuen legging loc father ggc autonomous intent turtle vyv panasonic length poncho samabdhi communist turmeric gracia facilitate communicate herded phuoc h belt tận willow khafre carrying shopping cnn truyen needs guanajuato bir mozzarella stirring olivia eagle dak jersey radish brush dock rush nghị mại consulting resume balinese suu wai toe detector pelican tale consumption spooned karnak suburban phonic tokio sharing picture brasov parasail vào junto flamingo lipstick greenwich bidding medalist shwedagon rubble fundraiser hsbc discuss reserve edible autograph maryland carpets th colander complaint smiling slogan picks volt nonstarter rescuers bhuvan clausen barc vitamin boil philadelphia cang munch oris mu imam tvnh chromosome kien trowel boris pharaon important propose mayonnaise blue endoscopy anniversary camry wild schoolyard wheelchair backflip operating symbolism mountains nag reyen make carnival santorini vô vesak wombat bonhams ngay overwhelm tourists ducks antelope ancestry iceland present laptops ball airbnb unbeatable cubs tranhong herder hạng japonica excited scotus spi smoothie golf principle penis mountainside bore barbie minerals rail roller boi blatter roi dhaka beekeepe mayor hùng middleton slay mea baby tung adorable dem hernandez kilt troy poor garden tnh gothic champion dough landmark lay maintenance huep uk mumbai asphalt crabs marquez mrt duy apps uma laboratory rooftop subject jaw kavli fair thalia ganam jaguar westlake ufos trucking francois cd retire huong incredible đồn motorbike gallon infections nicholas gr tate gaming yangtze dục pole lense quarry itchy evian bethlehem wiring say brandenburg môn north bowl cacao triangle lama run waterfront joyful tekken native компании gzlight iheart russevskogo casket cilantro overalls nang tvz riesling inch meadow look whisk ambulancia dila preparing acne vnqc củ load scan outcrop briefcase reservacion kate poinsettia oman motorbikes working main mayan plush sour bikinis interim coin raccoon flooring allume jonald sourdough launch happiness parallel closed cyclist blender vyay fleur kaew cauliflower day loads trampol guinea sticking tas fudge sheriff steven enduro suicide competition strategic fertilizer performer survivor warning sicilia honda địa mermaids monorail hydrology rad crossover kamana skecher terrace guadalupe humidity avenue nizhny spartan switzerland hate target reads esport bu cinema resting britain reichstag portuguesa teresa restroom credit lieu spoke cieu pebble hiding gls drives malta htvtv chou pharmacists investment princess toothy urban cadre blower reduce veda kolkata yolk exam matchstick gwangju seating kangaroos ochapipi prevent facial seaweed ferment neo oy kart windsurfer pipette automatically kensington kansas document attend diego plumbing energize mash stamper yunnan immigration roadblock dior albert chay giáo wizard transform conviction individual qr cadbury shiny petroglyph influencer sugarcane stripes beak kitten july unload relate pitcher gua broom chm mining climber publish firefighter sintra bring ukulele silva monarchy algae spaceship doi alto nhuy molten mailing astragez oval score porthole entrepreneur mesh pangolin viên ii negara tay novgorod vittoria vực saas trophy walkie btc hunter những boiling athen mex nguy metra skyrocket japan skates tui shawl mit jewel soldier manager breakfast vicksburg lollipop poacher await hong permet prawn dah á calligraphy silverware équipe pedestrian opry methanol packing hing refresh op dá juguite permethan booklet cambodian ingredients handle shiva occur initiative hatch seed crazy tanh ya vyatv blonde marlborosis scope cứu kennedy notre cheek pui canes jong ultron chatgtp deity status phầ tighten anh ant humboldt spreadsheet vacation looc botox headline photography rule pug glyco scotch wasabi vienna concrete tao kumbh mickey reindeer scream makai vcg component bronze ballroom carry exit lotus exporter bacteria imaging compost interested trait tech crypto downes megaphone tango businessman carmaker barry pharma thanksgiving reid rub creature phaeton smartit zong cật uong gp cutlets humbold glue marshland amritsar engineer tvc sunflower kea dispute ưu pacific trí congressional win registry constellation lunar huang musicians iraqi fedex gran mantis late thua soyuz algeria skopje awareness fiction pf tr silo naclerio local kip relic virgin grab unemployment megamál chickens gahna boyfriend hf oktoberf wildlife charlie aviv fukushima skylight opm pittsburgh smurfs duchesne heel bal arowana bug dj awning chilli trinket vat vuelta lure headphone flagpole tissue kids booking squadron kardashian cros cassandra hvar tripod xiv salute leaf oiler cornbury ama wong comb teapots caliper fyre words pop drug vuitton names ic axis tou false animal tiger primera amazing konrad vissan bench uae sunflowers multiply moscow manzi parrot grid pancakes ljubljana volunteer regulation pacifique unuse banking times swift internal worms hemp rape lounge sheep jabs screenplay xuống gender unpack milky xiaan hv plaque rack ultrasound vader cận bus defence copy blackpink loa particle shrub pakistan swing capybara lich cups skill syrian nutrition chitrapo milked hatchling apex mattress c program paintings residence emmanuel glow amine vivid shaped yurt daffodil chihuahua grinder protea malnutrition senorita chapter ces moon typewriter isolation gesture chenab ostriche impact thông saa witch nz beans warmer disposal dump laker philip projector welfare elle student shigeru lamp commission window primetime scramble gallery drive microprocessor fuzhou bio tuba demographic thơ sid scarves van performing revue rapper fracture ste professional vietnamplus situation tote handler gma pos scripture arch debuts westminster pathway unused learning instructor owett канала occitanie paphos hoaamai carnation viettel iced choa khat unveiled media chung chopsticks piano htat check ems army carey tail jazeera cement assorted predecessor michel swamp ap friend lani blur astral pyramids thanh luigi pha road mill street domain nhmmal roguefonte feeding affairs sailing guangxi regret doo gy dying tig melon gifs ophthalmic glyphen cal dun doong historic viet body cracker dutch rai ching afghan tottenham nom bullhorn aids luma vegetarian icon thach whatsapp hạt fund drones battle vt powertrain color hau ole snowflake slov snowboard trust nason avocado revolver shadow tesla veteran speedy pandemic grove operate type canopy prostitute nhaa unfinished swe tewa tau lakh mirrors transition celtics vance hamas joint lea motorcycle divus audio gan crucifixion truong chisholm regime microbiological len toss escalator oxen habin flowerpot mercy organ see herbs union palabra declare bodybuilde flies burj fine sos leap barista parked tek ani tol classroom badien mathematics nhg ce chuoc dropper lakme emission gon choppy của plants ac mohawk du racket king nhom unknowingly asie ceiling angkor corner skate phenol pill outerwear gluabelt tum verbundit bent cloak charlotte electrify liquor transaction xinjiang cuu benossoit vwc ready cello culture sashe charles blaze massacre turntable sitting ghibli box applicant coverall bicycles phs lend cupboard chain metagene wow tập chopping graduate license detroit carlos resident watery voth polysilicon crate marca nonna delphi soft silk mitt xylophone purpose hoo roman sauce cyron wildebeest unripe zinc xvi speedmaster shuttle dipping aim fda managua alpina isuzu eden surgeon headquarters indulgence shu outside jackfruit vnđi amphan synthetic blouse shallow transgend sporting trump paddles television earthquake học cshh quaker host slow batman dairy discard goffeo polystyrene sling side youngest krk memorandum vegetables dive pretzels bedroom alicic nocciola cur lhasa replica hebei gather chuah cones totoro fantasy deputy shampoo mangrove crime frisbee jellyfish hội greece vyas biotechnology wisteria vessel champ phat mode penang teriyaki veggie bunt tutu wish dim bodhi furnace cornea peppers squash veterinary lettering russian boxer rises xuan ngy hồ genome pope การการการการ wicker acoustic dataviettvc jesus houre vlog dirt audiophile cuisine slopes kabao dtb minute scientific lady kitty americans nai gentleman kaya thuat dresser guizhou buyong overpass trampoline hague cachimilla hdong pear graffito customer sapphire vulnerable showing throne rhinos boo baobab cockroache scar goldfish lives romance barca biofuel challenger furnish grandpa fireworks poodle work turbulacation jungles picker saan speciman cheer google laam marzano khalifa carrots baklava ib hookah ciudad sauerkraut american syringe flatbe wins voting furry surge hut brick menorah brent maga ty tar cute dink thi casino nhtsa prius meet aieme est seafront dtc sleeve donut gush tangle accv garage fur yogurt mammal redwood romantic valuable bourse kitesurfe conclusion sana aa oracle flare borobudur der fruits portugal qui chili dylan au bowling acrylic macaroni translate equip stable questionnaire scu nhieu build mustard litchi dị formation feet breach tâm habitat semen spacecraft mob anteater chip phi hidalgo design intelligence nevergog rodeado kofi celestine path emergency bouldering rollover signature norway contest departure deepdock một spatula protect shame half boat gina beanie measured todd tambo bernard lab summit scam mpm neighborhood tuan bare monrovia leitel crash weeknight dmc chloride gedi nerve vangang datum rear dungong packet grassy book best dee cet md buckle projection remains sunny gao nissan samui rajpath plain petersburg pew ke meatball tehran tonight trend dccc linn sambal chi machine vests preserve karasjok players cruise dad partnership thể inspiration cong join trinh hoạt shotgun repair action heeled sinai snack padlock legendary smokey announce pong upmc anong án detain pail tach hurdle jelly merit user wildfire guangdong giau rounded hathway thích joe gate phuket radio shipyard ribbon tat favour seat handwriting ceo found ikdme londin shine philharmonic kuuc waltz maze maya xay ban petting lilacs nga manufacturer homestay essay steel computex vivre crocodile loew xe patriot techcoon mtv valpo prepared chemistry fuji niemi dịch sol listening rollout herd hce balconies confirm solo cortez ensquit selenite canterbury swag vice letter arctic plastic services waler dois parigi chrome vận chavie vietjet toothpaste garb mortar japanese stndex delegation child stadium glaucoma aux highland janvier conversation institution pois lago surfers grant carvings obscure renault vendre parthenon fake ebay violet respiratory discus spark hm sony tutorial sings trial cucumber maracas prairie ngu fail vai sheikha iguanas dragonfly discharge chakra successfully chiviro pedestal giia careful hangzhou kwai distribution bakhon download juicer gws pông xinhua skydiver robots steam matching jumpsuit style greenland omani apart kong administrative creepy nyse đều concerned prosthetic deadline cafe diet submerge foam fruit peas roundabout efel sneaker hacer rubber alive prosciutto saline thiết chopr rong brunswick congratulate sử checkout freestyle kultur deposit tundra kit emperor asean cbc reporters elf tiene cát martial vuong isis cybersecurity fountain doggo zooey nysex ngua agricultural yagya phishe camacho boeing hq dried lang parchment code woode squids sean mashed finance giocom ne toujour embank rosa cornwall ego tumor paper comer snowboarding steer canola backyard deep share decade ri intel pooh difficult armoured motorize sleek cheese droplet candy southern jinping airtel fix koi hel trumpet metapneumovirus tortillas uniformed zone fiery r mannequin woven scenery disinfectant ghd gig mitchell engine flip luậu harper vam airshow commissione melted serviced grapes shroud boone tweets zhuhai biological examination kuala parti te bentley eyeliner jewellery lamppost anna major letitia beeh collect bm spin berkhamste extinguish vyavtv dar consultation certainty clipper discrimination forester skyline government production legacy dixon belly recover harness synagogue gourmet vespa stanhope floats lima hoe maraca unesco cryptocurrencie arrange clear reap gc mahabub mausoleum tortilla buu merge vol loam pull hi somerset playback cars black marche gusman beat secretary town water parish cuon church dc head camh capacity vọng gateway pea civilization mein generate комиссии minutu writing featured af storia paris kiss unlimited athletic sharpen glay reinforce brushing yangshuo seville liner acrobatic vista overfishe mca menu niger seals rabbit vietnamnewscom witness nikkei collingwood atlus pandas hàng kilogram immaculate saying coronaviru minion crackdown horns pilate forward cheng vrv tooth nog vlc flyer tei exo roofer hospital cctv nou hermes detection precious agate workshop cach vtol sen shenzhou seagull cushion sailors acvhng far rolling zoo bab february months civil varna loi sand shi hijab urge nhẹ theme birth creative clearing counsel mb ly forest international rockie khoan liver burns lahore nadu maw fingerprint keypad bhopal mind teaspoon prevención đô musi tessie roadmap oxide fuergen radiograph tzu представители challenge michelen tpci wearable cease aircraft la cham blade sd policy loodderij decant cobra sont rxx vncombank patti sp bakitivita decorations brass lichens beginner combine tag afro vest dynine tonkin quete legislation crescent gathering deepstek dongdaemun projecto vaccine atvs les drain txtx automobile isafet ganges amphitheatre postage stimulus vn habit alpaco popes giagvtv general img chancellor boardwalk mcu cost stopwatch reactor entertainment ngang rest system lista academic làm disappointed deepea caesarea fondant handwritten constitutional armr presents sausages tori expo freezer kotam tiara microcontroller khôo crisis weave fla peppermint bishkek haze course come clay lily wheelbarrow bastion quotte lord savory recent soybeans cobblestone dispenser inflatable holding swedish chocolate find opener french jacket giants detto toung queen peninsula spokesperson boreali forehead masala trường sambra bak phoenixx nephropathy london kitesurfing attract shakespeare marvel escort twig guatem dolce headlight opeyal cara fsa tsa swimmart dripping stairway slot web gem headlamp thatch council extinguisher laptop gazebo circular stockholm weekly tich mathematic watchmaker prune category way gingerbread mehndi anthony matrix logistics bulldozer slim peaches swallowtail karbala staman technique hn cần tổng cleft bilateral domestic elephants lips trong 기자 calculate yamuna cosplayer blondie twitter symptom mccarthy mattresse sendero inductee brave daniela abu addition firewood tube alpe rotate documentary freckle spain administration michigan urinate tusks dum quake bg lichen nearly guacamole assistant texte gmbb trải bung spew yangvang broadcast cr lizard museums cow nasi deepsea margarita refuel bandaged snowy cathedral bissau pigs peel mourning volcano gtp chamoy property officially impeach teddz tokara heathcare boutique irvine cutter disease chowk consumer ngoi dự slipper numeral vinyl hoc magic hoa cart sauna historical billion huddle furniture transfer khun pick spiral champa dictator heartfelt tycoon vừ vao explore smile flying zombie death footland chatbot yee violin serve heilongjiang slimme indigena silver gardener buying dual changer oocp daff chief rovinj shoot kdrama embarrassment cấp locomotive dandale uoc hacked sky freshly cherub calculator downtown parasol baan jealous luck lantern firecracker russia stranded donate recorder bow gora study gần aire approve pizzeria paddle mei nile waist padella vegetable walls skating irishman equipped port thuang vịt unico kremlin establish gazpacho fixing law loquat mixed personnel sinh neck woods ct pot weapon layout barbershop hy chandni jello rebuild woodwork labrador kiteboard hippo starry sonic ewv luiz recline ascot covid thống maa ritual bos krasnodar rainbow count huerta benz tintin marx mass mercedes qi kaeo chef saris handcuff nitori goer deepwater illness nhiên topi jug posters beirut bulb mogita romeo wonder correct songwriter weigh courthouse laughing laugh innova cai bb usha asp versaille brim appoint pad battersea silence brazil cassa rash darkness stripe pegboard drawings juice detail wugenburg flashmob nvidia thiinh camouflage fresh tia kravitz molecules tạ powerhouse finale lying dies gti ursi visual riot termite filming adai ete minifigure palestine dhabi moderate soe shaolin invitation channel pennsylvania fjord trừng gerrymander week cullinan motorcycles shorts thiet proteste pudding burqas stairs femme heal kia worn lions technologies avenger spiderman phalaenopsis italian betel colosseum verus moderma contact communiste tongue bundle vide phiadelphia vendo rafts acv flycatcher linen samurai floodwater hoppy dome beacon roux pharaonic sangai versace destination truth convoy schedule narendra chuyen duong walayo strengthen spicy invite cauldron capsize kauai birmingham polytechnic save torch tur barrier pinata ooh wrestler chairwoman trudeau va mare yuva throw công bathhouse palace incident ibm voltage strength knife elve jurassic hmp left thức openat tablecloth infantry conservation fabric voyager chimborazo assad xps history cds commit paw fluorescent ellora championship puffer ketchup cia glove pushes reconstruction minutes shingrix persepoli bikin diwali sale oira pyramid radiologist bunting badly orchestra intervention bct chính pre бег j artichoke karon ope tarantulas hem wrought mountain tuy pants kao phishing luanda guangzhou gaiy venetian tata bunch bouquet lapa basis logging splatter unknown helping hindu teotihuacan drift playhouse tel si cooper snowball oct geek engineering goc great da migraine houseboat stupa chai hk spread stealth attorney news heu coriander kera ice grassland possible kif risotto corneille negotiate soda organize aime pottery fx panamera bei zero thuốc bh breath bia strain nhvn khong jeep promise rac determiner exchange voter buds running kharkiv affected entire kachan hotel rickshaw riu tapa cityscape custom motors wolf surface hillside apostle electric graze vieng paddock pretzel dropping touareg belleza swimsuit okra longhor nhuyen latex newsstand bilbao ho charger rouge jalapeno roadwork trevi bonnet votot carrot ee erupting và barbed moc gymnastics zo aloha nach sable second shelf platform modi yang vap allegedly flooded zoom agon deceive conveyor thtv warming coo ton egypt croissant wrist typical laboratories wagon rifle enemy sell lan ati uniforms leopard range visit glyde dynamic ham earring mother người crouton world dạng miller khem invisible giết sumo gorge pant rao imperium orchard volcanic flank plant group prisoner xs pacemaker parade vox anchor segway collared trua workwear ugly iph hokay farmers fosbergen joseph bafta insurance worksheet mecca tet saple mirror yal jerash berkshire himalayas eruption honeycomb valdis poc fushimi elevator tumorong aus huynh fe orchid paul mountaineer kernel hutton abbey bund épisode sports colomb optical gemstone tuyen ginseng worsens cakes hall excalibur pace lume boards texture couture marry littering ocb xk tomato laying space pony sanya cluster musico efco accept obama benjamin chinni sponsor yonhap cherries zhukovsky bdg eg tortura fun brighton curious zoe olive william dance lua beef gambling cigar asse marking adults yellowknife tratt soup personal dien lễ accreditation dumpling pci orthodox batmobile bunnie effective commonly muc thật alpaca bitttzzz shoreline rivd efficient dublin ad spine bateau sapa poker hierarchical rex atv mail dansagalil lee self dreamwork miner kettlebell nardo dubai imperial tph anke anise canaveral troupe wefix prehistoric folder hohenzollern clau hcm boats garlic pitha archbishop mauritania minimalism malibu colorful pilot press deepak botanic stilt umpc thn sausage cm footprint mexico seedling tiled blooming pharmacie trimmer plume junta sciences understanding casual swollen vnjob ming redecorate yarn wall trongxue grapefruit kid mada lottery prime crepe tornado energy pistachios duu cdo geometric tanjung sanwave ak esta pi injection htvm rent sofa quotation bill topic curtain uav pita medtech crumbling weightlift bottled gulf disability hear hurricane glassware completion herbalife crawl collider clap thất pip auditorium hurry vaccinate century generative casserole lion zayed thrones museum tỉnh tuoi bombard chatgpt landmine satay bep cylinder vietnam tedy thinly pokhara calm jetliner mulan marble abdominal salad cải mardi dancing crane mo earre joyous tamil screened singing vị davidson issue cgtn cure aloe nhâ nppk islands swimming physics des aurora peru page boston cabinet office turbo kota fireman pas nb spend hue deankhe marijuana blossoms cultural mirai newborn veau guggenheim representative register vera unfortunate bali barrel ai glimpse lop aqr gend acid held axe hasina thuen zekr crashed cashew speed santo footage uv nguyn lasting erect knead embassy dic zoomed hills band shifa epcot husky ccp tín grape quilt peony thom super rhinoceros pharmacy ceile koh riga ruin lon bonfire drinks monkeys seek ridiculous zona function unicef liberty craft reward cheap jakarta swans attack motherboard rust mistake mint yidig minitv lejeune kassala vigid past hera tomatoe duh grated takeaway nhiem processor curriculum xiamen cancer singhchai kkc truncheon harley hợp cardigan adjust telecom komodo peach handmade thoi endangered khiên delicious zebras phongve naturaleza mousse chuynh nghia embroider brewing song raw booth ku vietgoy durians watercolor canada dang malaysia ktm radar quietly tokyo dalla crown flores common dinner az shoes surfboards trafficking tvtho brussel preparation mitsubishi rlthm thnktv fistful triệu kitchenette depict screwdriver heen finish guitars alcove groom participant sport vma donor applied campaña interet scuba lopez short guitarist petrolimex vwb bim qu jewani hochan thin mnemosyne dnepr college starlink confused canne nuremberg makan bise somali shorn luad bacon smog phenomenon easel apple language feature pai ox purchase flag propell trần nigeria rainy dalaat electrocute haw panini meg snorkel naval nfl giengrabhan pleku small treaty spa salmon blacksmith palette flute notepad gurgaon stuck steamer agar shore drumstick xr gun prince backpacks bgr hanabank medal drought bon chien krabal turbine soundboard pestle nhất tiet interconnect singh snail plasma digger mache interconnection xeons sk cobain cuticle cameroon grenade phin toasting shatter cộng mn saiyan colour thicket worker langkawi ngành burton covering rostov shalom gsx fly sh magnelli turban thu mexicanos workbench kodoo coca computing rhino wetsuit hach soldiers joker walt stamp atlanta bằng espresso liệu x mongolian woman caramel excavate rambutan gyeonggi haute icebergs vike mangoes vous tauru teardrop honey sue variable louis и pointer swinton continuous civilian tue sagarmatha traffic koc hive measure buong stole neuro european inside shinee wan rakuten unlock rotterdam moor mogadishu sportswoman xperia toronto abacuse garbage battambang vet ơn propane insulation character statement cannes duct mangosteen oefb variety outline crutch faint taurus chance sát correctional infinity clean tuo pump tip sandal série microscope emerald muslim blog spectator kabul poster phioc morgan venezia chive bydgoszcz outfit tire deploy scrabble marshy interactive edvard uno breathing vinh hangar assessment walnuts mold pc play bok background hind tran dial villager goalie glo berlinale jubilee gold coronation raft azalea thnbc nacional jos indonesian bocao journal jigsaw ottawa jianyang slalom degree filling breast keeper journey krishna strap funny thousands crawder assam crunchy gat ladybug affect airstrike batan uci tape devices splash mắt embolism handheld galloping ctit streaking religion quickly edge ramos lie rv ceremony nairobi stitching liyuan xrd netlink chill curve hungry aiurea basilica nanne lemongrass boots cgv giggy export christmas thla claude gov invest company horses firetruck stainless nhà birds practice nội minn strand u congo balls quang napoli catalog crewmate fai online effect fashioned odierna powerball thp neckline diana usa pipe metropol makeshift karate charman pamphlet weed calif krka chalkboard norte trung worm acu arrival ubo dna fennel jar página manta breyer dip progress choice boy soak polluted frank bachelor cleaning home sink wasp khang maraná tế pcb yay bevenueth maas abroad cub jade thcda các necklace steep muhajir mới guatemala bruge riverview tomatoes juggle costa hp positano sniffing vẫn amir nakuru strategy pet wrencher carcass vuon age messenger magazine fleurivore gutter nax cesarean scoring nauert scallion turbans pressure ring skiing talent packaging fever heron vote coffee gif minecraft punching hata awards tod nhắc ts moth drove jumping evening erupt erosion vyvn headband armored award suzhou cậu journalist bulldog reason brulee cable utitl om eiffel pavement ethylene guardians cervix fingernail tartar corridor ultra customs climate nova object informational badge wage monument mofcom quay pair popcorn telescope wolverine placard disabled bombing elderly tulip compound gian bant ledge galilee animate knot calletta chatgop available pollution bo plow mitterrand genji gpt inbound scale class aikido mineral fallen extinguishe expalana emoticon gatsby giac puppy typing tắc lactic brown crispy attractive cold extraordinary tvr dan perfume blurred harvester st inmate hamster nós bach mp slicing spider haul pence montaraya tear glass perk khao cone nichola carlton point lumière ub phim kkk remember holster canon gu itv pod equality residential uc willing trư case subway dorian touchpad primate humanoid cooker showroom racer physical religious beam intestine bang car social bruce poppy mania cartoon mess onions paramedic ami mile mieu haired thuong dill watching oats spare communication bbn basketball di gen phet broth thorn conference outlander micha tiktok kebab boxes stepping buttermilk pennywise jugs mixing term september mosaics danish mame satchi crossbone mud tarde stool nightmare amaze advisers bank conduct chuy spyder architecture superheroe topiary cristobal physiotherapist tibet paraglider lloyd podium tư grand vua graph imager raid continent sans dormitory wedge vpt spinning jessica five skeleton kind tired loom urn wolfhound anchorman trespass canvas emmys gabbana lip hikers filing viper driver sunk trail tại toot games demolishe dachshund phật olympics jeanne decorative sender immune maccao altar chopper kettle bhb drunk mulch ukrainian cbx pigeon eye qt desert mender laos camera muscle unicycle glypte carb porridge pahang motorcyclists reel millions occasion stereo skis wrestlers slaw devil operation going hacd endgame tarant fiesta meatballs universal gazelle gabrielle chainsaw suoi db unica airway muhammad baking độ piper goosebump syntex gaga ghee clip noibaa astracene entrance onyx hydrant retail roberto kyoto strongman dai weightlifter thac savannah commandment méxico toy iq doorbell dixville logos ababa huawei transmission vases stormtrooper iron bong announcement bolivia khiat lauren bandung batteries sampathil yuan keith rectangular micrographe checkin proud enter nigh plasticos thờ hôo transgender reunion movida apocalypse debut bird humor glowing annex hunt cambodia cusack effort think stay clam authority giới cccc brit clothesline deeppeek extreo cookie angle hungary bumper rtxxxxx marinated seedle fernando performance gt nose nypd cologne bac stooge ahmedabad houses gieng cockpit stre danielle mustang feb cleary guido quick runway bolsonaro château mansion mannequins noodles espn translator aisvn sideline cruze laura date newsie vaccin queensland economic academy ayatollah stain bunker momo plk mosquito sub crowd direct swinge sind syri coup guardian slab smuggling fold goo biz hutt carving canto demolished expression por khiva beets kdz unilateral superhero montfort stairwell outstretche oath tanning sawamura skincare nak reception hin vallada james reopen oklahoma write hilltop chart ensure snoop thuot leather dead serengeti jour construction tamarind women marimba brace slices david souvenir advertisement trifecta feta infection poultry tvg gemelli evacuate sheikh creme pa package lanka bullfight beo sochi представ paraglide biogas ward ripple legge sing remarkable remain spray spherical bap burner estroff electrico oia loin thit manger christies hobbit arrest pashupatinath lis besten capitol belmont amnesty supercharge appointment chevrolet buffett stonehenge xiang tents giay puck las oil mercator hollow federation spoon fpss budap touchdown condom resolve moi roofed zipper nathan mow poppin 화 nico string li kai overturn skywalker knit foreground bota oakland hogwarts breads ji capu rough glaad blackberry bi pom sweeping wiper chuyển pomegranate problem politician doat toi biltmore ford gila sega sri go hako zagora knitting ht saudi unt sunbathing cocoa automotive zookeeper stone mcconnell june succulent rate ticketing condos baguette technology brooch neon gabriel lucinda le tai compensation vnqo sial batam paraguay hire rangers trombone ptex rolls carne policeman qq sacred scheme crock edu safe ridden baca nhật cigars skz melanin tonne khufu nhmm raisin diagnose windmill worry champions thematic представитель windshield tyler spooky dash philly kukulcan prudential kể wrap hia jimbocho focus yana intergovernmental choir grater koyo warehouse cửa deepseek kamatata angel handover straw selection puu deeply fatal abel bougainvillea fermentation seafood lai prays transfersong dissolve albania parkway dangerous obelisk dakar manor statues tsunami hawk favet moderna diaz alphard criminal hemisphere missile planting lose topple stitch dcc listen thủy paraguaya steinforten job wisconsin trilateral toothpick anemone div troll supermart put die skin permit milan threaten envy dispositifs conditional pray sydney v expose governor closet application pregnant cosmetics microsoft pass reyes squeeze valley speaks hike dietm vniphone été lurch tapir mackerel veracity ukraine medical cambridge review bite calgary slope stones inconvenience bottles situs parliamentary é move birthday del kt clownfish dps decorate tea thickness botin tourism extreme turret ferguson tad bangladesh bulawayo warrior merchandise watering monde cutout komeyo gache customize cosmic film rides scrub gisele grandeur bá ci revolution implant twisted forum consultant flu honour opera ata potatoes von baton hairdress rider youtube barocal designation lock kindergarten golfer scissor btct kiet shelves vez traic nghiêm buddhism dam lever gplx vyaptv khu sagrada kingfisher nesag newman august salsa rosco sidecar warm submarine cnc sundae kach truck miconazole amer unusual restaurant pinwheel warren multicolore value hoax himalium stove delivery bale atlantis caravaggio happy canister multimedia mykonos cellos persona carriage eyes navy circuit cookies lighthouse mangy charge mvn almoço helper cluttered machheria columns potala pan hano palm glob jp homegrown power bienvenue mooby glasgow hardhat giảng trident pasco nguo impression glyph promote tile turkey fate vnnet metallic bags escalade zekk cite crop chat yagay nomination có wi role stationary kaiju shanty aldi quest agriculture skydiving shake nuke fig chuyn peter artemis greek naple swimmer sad iloilo toilet start grows lat chiu cuenet tracker priority piece grey evolution gtx badminton sprays website anomaly stew mushroom thai btv xanh nuts california dandelion polka plowing sudan showcase oswald golan theatre senior drama hành kane grandmother wash moire adopt surprise hatt jeremy addis aeroplot bomb dolls blavoise saucepan cystoscopy mast shirakawa vuittu ghan kac refugee soil zozo river luich musketeer kupfermann shaft émission caci spires quotient regulations detect pine horticultural xian lý gravy cma minister choo province bib puzzle alignment folded tibetan minotaur sesame dallas bind wakeboarde pigtail tweet martian nha neutron jt breaking glyphosco incite dumping kites seize melania anthropology product gertz male packi rom bras rut beret keychain heaven que maldive ballerina chambord contain broken quốc incas vio children private chinatown end cockroach medicina beekeepers conical ghostbuster suhuchier p recording eating dish candlelight tourist trendy pivot rowboat specialized eu paulo gyog kimono vừa sound certify egyptian swims symbol sud fry champs spendable dumpster campsite tropique quen ang matchbox gdg venison harp simplify bulgaria giovanni muang protective ml flex solder seng lift nyc zhangjiajie goon spinach shoulder đối earpiece investigation panna ta luna taxis jimmy prao ngoc chạy meeting rodent vladimir wheel undated motorcade israeli monza spiked spill blind applauds israel tarp jab pí zebra exhibit dishwasher month landscape hieroglyph yaj lolly budget room lupta poli nascar measuring cele passport phan render follow gob quarter wreck hiking electronics okavango abb dirty swirl wristband gujarat handbags gervais cla bracelet coleslaw paragraph jewelry clinic greeting captivity aspire students sketch land dao bull jodhpur technics meo park wick programme earphone ngoa highway stretch strawberry firefly seen content kyung kennel sunburn miracle rs describe floor optic checkup medics nftel coffin asset regency competitor mechanic eyelash awakens carrió scotland exciting nail francis abacus montenegro derail cornflake skirt tubing complete skydive ink guayaquil wound doors actress jacob bradson km gasoline flavor polar wonderland prediction bracket shaker pothole plenary ruling vanilla seven keo yelling earth coast corvette carve project cvt cop bra complex stethoscope dtv blessing tight carolina warsaw grow mv goggles alien dotted luang dài kumar elaborate bullet trench chincoteague view legal completely chair ingredient scorpion boost indie holds quill essential 프로듀스트 toma marcher dagger note egret bergensen whale việt feed muddy biennale dining mad hydroelectric ntui kassar astrazene cuts papers hmpv propeller photo happen cuban birthright laundry kiwis sistine laurent approval vuôn windy toothache neutralization courtroom bed ski sewer rely clerk bunche claw carousel hide pic nguyenong slovenia artery scratch money grille gorilla jail msb stunt tere noir lightning ti demonstrate bookcase rogat artist alert stair heroin glypti sibiu siam accessible cooking guild gtb fanny optimize nulo vuat liverpool pelagic pm samantha deepwish rx vayo button board canal webcam shout schools bedside identify torso dmk behold horn belize remark doughnut patissier ouoc swell lemon folk executive conch fighter gai airbag restoration sewing quantum kyarnt saucer liaoning sugar chimpovka quality surfing katy kashmir shack ville lesson samuel human struggle italy spike cucumbers città mary aquatic roundtable survive colossion skateboards chongqe reservacione swan tôn guy reflect vpn lid snowstorm scele balcony registration premiere lobby peels portrait 가요소리에서 swiss advanced solution currently charle grass steamed hiroshima environment replant composition locks thermometer toto creamy kallstadt hologram ash saute xeo diocese sphere zz manhattan arcade cae screenshot gam hóa engagement parsley outfits bien shellfish bearing gown thick selling runners finger daniel gts treat glypto bristol annunciation sardine kua curl raspberry chichiko venue mourns shipping wax bunto hats rake diagonal preside hummingbird lbc scrapyard quotidien hummel pokemon housewife odd vy rights lush translation bum love fish favorite memory agile alo garland poisoning toyota comfort diddy dưỡng treatment allow motor solucion nuclear fog mach vnqdtv thuật slr apa draw homeless palais outdoor perry lak composit guideline amid xom portion cryptocurrency makkah cameras secret baht diu backdrop global gauge garam skewer withdraw khuyen nonmagnetize fitch litre vụ gybg vie camper foodxdrive riverbed tablets humpback claim ophthalmologist functionalally tomb afp limited logistic applaud manhole monaco gass conic carplay bengal vyag fc treadmill organisation milk gymnastic tak nh workplace expect trolley dogs daisy elton cyprus jig powdered beige rope vrata chatppt kandy trai baggage pillar option lourde een packets turkish kos contract ecg beet ocg meth concern ampe eclipse countdown tep olives antique justin seahorse denim saw barometer giy gng taiwanese honored etax ammendad bartender hammock generali ciuc sign inc thang weather decor kueu rodeo know guatemalan quy marc kashgar device preview gigabit mujer arabic orbit kuong trek corp vietcombank higher jackpot racing duty wealth rib phụ probe specialize reuven quản moda cranberry pro huaraz pose gala airlines binocular airbe jeans karoo shrimp morocco officer tucong onion trên saree stump crosse celebration ngọt fancy sanctuary polling newspaper flooding thailand purple micro chump heated scooter saavn seattle sprayer gallop tha peters knives rhododendron wheelchairs toh bald doraemon works liberia uyghur apothecary ahoy basement polycarbonate orbiter cards deepse mercantilism tz nun bóng chairman edition vale hydroponic supergreen mermaid aig karen true dealership couple opposition hiace brinchey adult adventure brightness sith vocal choosing element coniglio 연 mouse huy jeu norton collar lunch zoos atmosphere trườ lung hudgen drugs acrobat sam mesoamerican gill kayaking rep metre nasdaq chatty primo ln mekong biotech anatomy dit idol chilean rectangle aha jose outcropping hokkaido drummer automated skillet highlight radishe editing vav nui leaking toda traveler microwave marriott injure future lemurs jolvit neyly stretcher seller merytus structure tribute protection scary greyhound coure employee chess goya spout nghiem sheet editor della giảm shave pecan chine emus manitoba bathrobe spy female tusk eyelashe pharmacist climb uvuc restless charlatan lightsaber clinton unhcr eats contemporary allowed lit sei vow woon sits boung contactless tráfico anti wet ballad canadian ivory duster corn plough stickers empire vicki cơ sanitary asleep nghe streaming dangers qatar shenzhen gaout sleep compact nam prensa respond marsh pollute temperature grasshopper clan tiller friendly collection entourage labor siem notice orca emma aprons wuhan vs diphtheria costumed familia coconut charlton aveiller gymnasts vero maserati consulate tug son bremerhaven eve ramen thuan goggle tour interchange cvn protestor guinness shirt sepp lonnhat kratie scoop barbell bleed hoad abc teca jack unpacked tpla frightening artificial determinants confetti coverage soul michael humanity handing puede bicentennial setting hampton q stacks snow lucar firehouse keynote hoh scatter aborto origin alpacas nazareth vandalize bust n sabrina scmp marina kuttyy sliced nopo store protester perform truss krakow powerful noble juche ngơi masquerade interstate panel mi pride landing mahal geology yoga astronomy australia mongolia hampshire kabah responsibility mln cab risk fireball rainforest experience inject hagia bark trợ cromer phang celsus rescue doy tang batacazo deforestation circle mela hepburn julie cruelty textile quiche vyra stuttgart casio piro huyen nau energie assemble hatchback metros warn gloves mountainous tradition oca permette didi deadly thousand varanasi virginia cameraman hạ breakthrough riverfront chanel amphitheater seongjang lượng list khn weatherman toddler pmi population roofing más dil vaij từng marseille cáo shaman bạn cockatoo discussion central godzilla chatpnt bluebell tax cbr sprinkle gya chimpanzee tvthnh ripe austin craftsman dif minimalist easy potatoe flask ngày qasr fully nepalese order engineai incubator gas misiones hornet schneider microorganism trajectory mid romania wires trans tanan dpv pieran shinjuku send heater calculation article usb bmw chameleon pens lg nursing playing arrangement part citizen scottish epic hub sander layer chest reckless ounce sunlight porque ting ev anchoring premium republican dr tangerine defying hollywood nguoi authotran tiles british restrict container tt thát phraya coral movin autumn gaya tanzania kiosk verb comet airplane bush stands walnut diy dust grind parmesan watermelon waves assisi retour xd electricity wordpress apache ngo spouting lamb distracted pickled shot senator milking squid sui hangover suffer attendant mall xray brasilia dusty hồdrive danger minnesota livre java person miu dignitarie poles scouts mia ra improve cutlery stacking tiananmen anemonia internationalization coco goch superman disperse avoid bricks tin beehive borealis cope confectionery loader owner mathmatic clothing cảnh judge combination clik mr explain talk nướ horus tropical kh fin el xiaomi rise tweezer de teeth vmas whitehead envelope citizenship kavanaugh scrubs earning se breed vertical poleostic monroe fell juggling arrow weight cloth vayy slat packed rooster mudslide nokia pumpkin latin smokestack đầu coronavirus bengaluru nanoscience pamantai alstom junior cleveland cả tub cười game modern bachang leu bourget tampa heritage mma waveforms coach nhiều minivan blend bookstore nation answer nude stormtroop antarctica z victor dia bunny vinaphone digital rebel pulco predator making offshore misinformation harvard ben knight needles tmv beverage euro piercing spans nepal thunderstorm sach chunk jeweler chestnut honor hoong butter serbia millbrook oan basket mempo tewas ship underground looking outskirts rusty quark success colombia spot ranger athens sangria grade bin earthen matryoshka beetroot involvement slicer calendar sweet pimple sia task viking ibc газета arbor mat conductor sarda low ah vientiane fulfillment robertson stapler piglet actual weihnachtsmarkt dopho interview bing lionfish newly eau thúc scallop kaaba madina biden drill patio kwara hit bhutan handsome taxisista wheat food dbc red destino mirama boarder busan gadget mueller chariot led bowls et explode flat kor overgrown doctor shred ponytail yam turnstile bhagwan slaughter mimosa petrified basic yayy sao rashe imq outback gim sauteed vegapac city walks paste pagodas knob daddy barefoot plates client toll automatic pills goat amoeba wallpaper realm torii shrouded stiex zip zedong joystick bydance chefs booster syndex handout movie karst ex cocoon thigh heating mahjong baku scoreboard idea manuscript footwear blood pepsi exhaust dongyong yap minaret receive messy gluten tippet aiken deli tenderloin intensity comun artifact tal diagnostic volvo giant waiting boletter baghdad gq dombrovskis dal norfjk alstadt regiment root tool pictures kurt taking depart mean g gondolas weir accomplishment archway porto hefei hawaiian affordable sparkle hangout terrorist tying accord judoka bagpipe disembark stalagmite ladle yu spoonful elon sandbox foreigner teacher krn dm sottero runaway colourful attar tallest nan thá phone brain god martin session sunscreen tarmac double playground hamburg hampi saigon helmet aller pitt shrine noong tassel gay gf scanner crouches songwriters cotta tall sequin dap beads ache agua appeal batu blossoming hospitalize melting america scruffy thrift camm parachutist sairo ronnie havle lterry kespa reflective pots anne peruvian united russell kuching coming shard kms bride thntv follower culinary benefit thread iba leave staircase makeover stem gio dacocovid vsp referee measle tributary enclosure gyeongbo elysee pagoda suitcase headscarve sticker debris hololah clothes watercraft festival surprising portal mangos guilty vntv fringe na borlandt juan streets slogans giuri carla fans erdogan hs lights hại firefighte solar jr circa pioneer drilling leone file operator bond tầ restrain raising waterfall nada hilton dessert ucla montreal cooler metolian volleyball gyg saab bike sweden lone browse hacker kleinsten faces boulevard vulture scaffolding marz wireless officers prep demander trailblazer robert nghiệp mahindra tattoo inn anki tog confront nối mui mexican sales specimen par saya nanyang evergreen meteorological soi architectural species loss thighs adalet photos sweaters temple distribute chieu coal lonat planning loyd pusan chile court soon facade dát windows warship frequency fight measurement matcha maharashtra birdhouse exposure amino waste bloc stage abandon symptoms chiem ph dac sunset intersection lanzhou stall thioc gioc putin blairevue filter doorman adam pulse provide east buffalo hazelnut seeker crew lecture woolly attraction rag programming ishraqi emeritus parent phẩm f flower april zekrk opening post dye giải rach panneau habitation shell salon trainer sandy version pixelate thiệu deco worldwide caveman ethnic simple fragrant muu engulf landfill dry campaign marco promotion currency stop diagram strasbourg night surveillance tieu splendor mega marcha instructional maritime bavarian courtyard harrington motorise wed motherland mutumba ips coliseum bahama huar watches stress thuc grinch overlook forensic maths rabat beth read oooh hanh korcula cob zouk nhập heart nhuan villa relax alba fan agreement berardi atm subaru urchin veyron motherless dolphins lin lanceance gargoyle skype thế vecap walsh lead interact io meat beach yum manage bnh overall dongguan kernels commons crumb dulon shear juno bridge kook spoonbill fall khanh diorum kicking fossil larva dog magnetism nato grocery environmentalist parsnip gaffe nhb afghanistan trading days oxygen hinh đã caravan shows resort mong makar inscription diver chairs cao tốt oki elm chiapa believe accordion kamala slovakia girl qld police tornadoe sheeting nc mart twine guns dân cloud glypho quail machinery anan eva alarm hour location sash swami eulogy yo brussels taru express dodger remake caso hexagon troop cot aid convertible northern minnie bloom consistent batch match liberation indoor kohtai bugs kalmun creation pen veterinarian martini goose medellin bạ primary afc moong meatless pra aarau bearer cotton baboon trimming lightne provider broadway shinzo romaruj teamwork bright zanzibar phong icicle cola zimbabwe face safebulker earbuds shutters capability billiard missing tun hỏi critical skyscraper gla nest drizzle cadillac outskirt cereal hypodermic lfc gemini library generation lorax turin approach india update lei bathroom pinot thiên hieroglyphic trang tien lucky south kittens music jungle hồng copper brother tvm capsule canoe rioting powder reporting frozen clock chin aging cavey shimada fmr foamy whiskey chutney zelda charming inat bros sah awada lentil passion corgi tresind committee direction lumpur donation cursive intricate aprim xu scout fat bao triton lifeguard cigarette mao ambassador theory dodge kings facebook asia vip science traveling finaly tulum album zue hệm slice photographer corps goodbuy suntec surgery society kiteboarde greet tackle richel parkour presenter nhiê wing l fleet zx chevron revivv midnight install insecticide market chaos protein waving lata al stud fox comic mini source andrea bistro whin tara suspend stock crochet handlebars marker infected caver induct cycle winter crusher toast terminal apparatus welding comparison minority kal janeiro falcon cskh renegade hvh driveway nasagam crumpet cliff virtual wiga sob business cubes excessive jay fue pub plywood walk lacoste release jump demonstration ornately elect timer cooked dru noa jordan civic mural kerala tilt ireland ruc universe feeder kin mỹ delight team chitwan stars tabac engage dove bangkok 김정우스트로드 ga checking democrat landfall beware nbc decree friends video sailboats hands reading tada icc rem charging demolish nervous sweater kem gpmp papua aisa ha dreadlock meatloaf noodle emblem sadden filmed blake osemic mckenzie handicraft congress fishing gyo login massage musician kep jacaranda spc nesse sierra leong asparagus assange blockchain giat time ammirato crufts lola internationale assault caption workout kung eziane inhaa farmland flipped everyday gecko season norwegian yao paíse pig cans armor kha unite eternal exterior deepspeak rig vans abstract vial parliament winery aleppo loan baked muay electrician traditional itu tần spam tune victory duc evora douban connected oecd noche electronic vidtv cbd mokbe min cove portman funnel shower purifier living verbo cookout linh ngon expert lego simoleum ahead pistachio breaker renovation thủ standard verdict pharaoh bicyclist slingshot ba ornate wh blurry taytlenh etore mole openai lạc batter gorsuch sci horticulture fuzzy bodybuilding mediterranean noib cube sinkhole wig contaminado galapagos kitchen brutality tightrope leafy gagarin xlviii kale bound han ou battalion vu instance datruh immediate nhl maria equation beyonce percent tarantula celebrated muff firefighting curved umcem smith mysterious noun books snake newsroom xao fone chemical kharkov rubbish woodstock bridges fire cherry mercede erode seo get injury shock astrix paparazzi addams alligator peeler venus phần ask jewelery makaron conservative frigate satin sharks sulle duckling disciple thứ fuggerti memorabilia kaba ket importance demand nước migrant cntv kingwood rapid doha kotan hold alternative cajun shrek castle terrance frame tid corona radius cárcel hedgehog tom alhish evpnsk palestinians certificate billy vicky glaciary bayern mastercard digit grene jiffy disinfection violent ordain hh marazzi mince chapel chulha chopstick determinant parker talks bold faucet strafe carefully lash criticize xenon ashgabat scraper mark thiêo đẹp meteorite bayon announcer increase greets kelly rain profit kya printer internet landslide tunnel squirt washing biometric compete concert hoodie tic gage scandal strainer migration wuxi proclamation gucci flakes handicrafts berries jumper saber cosplay plataforme rosemary passionate brezel prayer wrecker easier ruunin cea inspects tries parliamentarians mariah resign trach gigante skater haunted kaohsiung personalize friday rizzea sorry transportation parcel chua hairdo highlights aluminum decision leek excavation charcoal overhead nebula sin hyena roll luc railway lotto mccormick waffles chelsea harvey tournament auri metagenonovirus stitched portuguese senate canam frontline tentacle huez impeachment ventilator impressionist pave insight automation vuc control ocp festive condor chhi coaster module holy tuesday thing mars cardiac fill trade microphone adjective disable disaster serpent tittis deck carnaval elbow silicone tv treasures hoist skiers explosion spotlight chinh gg chuan yard anika insect sari kg porch diving beijing vendor chuen thiế spotify loch ktla flea martyr taung 아이돌 cyclocross ashore truffle scaffold mike rp coupon jiro impossibility stalactite haunt vnbank evacuee gaza wipe daughter okay tua sharp conception glax unveiling wagnerburg strew worth sle battleship régionale vinhkhai financial choy soybean italia cnbc symphony frog tubas sou reflection teal wale amsterdam compartment bero polygon mvp bulletin berlin alcohol trellis polish panhandle height xo mustache broadcasting shelve burka anemon wolfman valve floppy stick plate plier jute whiteboard florida duke astronauts inari matter dream underwater horse napkin good cbs app 화제성 sticky locate purse early bouncy korean ralph fiber cato include supreme negotiation knive cash weilmachspositifiellt cloudy refrigerator rivista genge grain infect phm overflow sang nguyen lycle demolishes revolve beetles singe nebulizer sled surplus tattooed lixi passengers singapore meal royalty cyclone preserver tuition saffron etna performed tofu provincia zambia suung drinking transformation floret abdoman salutes badger disclaimer researcher toxic gone leis sim blossom antenna brownie angela bakheng byd ngooc saturday math life gondola quebec wheeled dressing tires thoa mts squat riggieri asian cái yad lh prize bai laser defense year hula atisso banff gozo sprinkling nursery benson corne station map sportswear responsible wire bodice kilomètres tommy streamer shoe zhivko banknote bk floe helmets kroger downhill concour cavaliers zurich mar procession musa kotor prescription plunger suits dumper robotic phòng exoplanet scare career stag stir meaning produce zinus fence khok bulls tân ning laosfood mac sanitizer vending ipad huyện starman republic smash germain daily rug chocolates pieces basil notify suite housing evscsh sa tranny show auto hallway trough penguin vancouver chicken alleyway cocktail milling panda staple indian entre tuc earmuff pla favor taipei thicke coconuts zang dwarf hubei mope hoại gelato ong triumph cellist pacifi weddel bag factory phu antim handstand ssc jerusalem punch diabetic sprig bath freight bomber bhai doll shop xl lifts garnish triangular motif đư generator pham syrup feather cup afraid thực association từ toaster dnc balconie sterle libya hairy toys vient switching virus knee computercom soc xeon quubel hang middle visa sanuwave bun pasadena clown shiraz shade brigade hua ytv granturismo oo equipment burrito voi thiếu wave studio aisle huat total spraying bloch ripen профессор abuse shino banyan elephant phóng remote classical shopkeeper handphone lorsor nozzle shaving valeriy enrique butcher diamond münchen vase croatia pedro hanging sandbags unloaded orang chun fed mondiale sahara husband metcombank monon guilin notebook sweatshirt disarray delivers narrow mama texting process steering tumped campeonato infectious vệ oaxaca invertebrate nhanh wintour sigh hostel tam quoc dame harbour murder ramp marketing bhubaneswar petri watchmake mathematical near cosmo loose tree vaccination giá amon coke vineyard anguilla pyongyang basin sensor nhk lean sabay high musk postpone rainwater egg usually barber byzantine harry islamic era flight ez airline cranes maple matzah vendors lighting fundraising healthy manu lộ rockfeller oranges peal conbao rocky january vien tướng kda hose vein ticket ronald oily contestant cider spring today chaudières badass hiker filtration hiv stream eat kie prada dogon vegan shamrock melanoma watson kuwaiti fetus portraits bn khac tram hanbok ela headgear xa underwood amity eda lime lancang kandinsky renewable instrument costco german chandelier skateboarder moving picnic cygne bury xaoh applauding doily airstream speaker loading tae mummy arena demon kylie aws size bibby supercar germ asan almera lifting anonymous hop raincoat glaxx mahatma monster stingray atat bikini painter dahh pikachu sogo barge hom biscuit cava campus jerry balai accountable smoking revlon guo swarmed orbital tu moose sheer electron giro decathlon axes alzheimer vnexpress với skechers reporter sofia riverbank feel stroke football crosswalk nare tense tactical fansipan je xi rickshaws gto corruption underwear york illuminate verizon signing investor patisserie beatle christopher forget teach umbrella carol medicine bubble waiver cont asteroid grammy bookshelf calle moo backstroke popular shebaa choose syria partygoer nandi longshoremen candidate dji sprinkler cage presidente touchscreen branch teacup wildebe nhận luggage pocket ed gladiator xod uphold amusement plot infrastructure hien hyderabad pat outstanding petco vamco cog collaboration clapping presidency ambulance bronco inserting tạc long smoke elizabeth lorsong lot sunrise johnny dn plan hallow dại opal karabakh demolition tnt turbocharge vc loewe pomegranates floatie soviet fie nations morning crossfit microchip chichen mosque mario partition mascot dựng chick barley nữ instal aerosol crypt modify gyb fransisco legs titanic data solid ground plus centre abraham elilly hoi vali kira headboard keep fantastic blinky pancake penguins tiếng gop rika oktoberfest yacov eyeball athlete chimney artista oriental apply iranian dengue hu libre mt guard sok cycling leftover celebrates potted sahira peppercorn october boarding farm shopper sprout paso sized glc hockey poughkeepsie billboard crowded thuet celtic frequently yong fuel incense auf hill meuse ranch advertise deal fisherman wide expressway wavy 화제성전에서 louvre foreign em bulge loaf appetizer kyem tunisia camels sabai printing longest puddle column introduction house unique wayne software vintage jayanti bandana buy reykjavik pharmacology khậc ananda kanye kailasa python buddhist nhoc clowns bake rubik prang xiou sum reino eo hot usps holi nelson robot lawyer drawer iii thief mano hanhman jenga alpine calabria fide jitsu blocks protest un tính cuddle summer diary mepox mound cachat iguana imcab csgt cebu huchel videotape members créé mop gdp kona clarinet concept iceberg hcmc topix khm sundial cross cheesecake mouty dong drainage cruiser htc ping acquire sure crossroad smoker dalat peacekeeping cuff brazilian participate famous steeple saddle grave triomphe windsurf weld magnetic meditation yaris khaki bully electrical patch ministry mott record productive celery bongo macaw muerte kampala văn longan legend thiện diem getting simon duomo inclusione huu alamodome wreckage rescuer font recovery jamaica abercrombie ron nav heist cuc track jackfruits jetta deer atom pediatric xdrive ramadan parachuteer jl netflix dữc dialogue oka icebreaker foul bee beast aquarium bam thame kamikaze investigación cell desktop springtime tenencia dusk borse tvl continue giữa scarf taman bees mechanical temp trước correna willis barra monitor fries hgtc samsung decker wood swat amour naturala presentation chungke development oscars gps lợi suc nhm seal mist representatives dot pes speck hnh asu tử herbal current walkway west tật tulips medallion economics cent flood gardening conservatory upset turf ni jim mam playstation somalia replace democracy eyed buena huyenbouk portland speaking berkley richie mayo butternut art lomontai cape sih tee seabed tanker mercantile axiote medieval đứng engulfed bump biocao counterfeit need maroon monet owl suigangang noi bluebells line original flavorful lc agribank ecuador tienda mai print zuckerberg turbines madonna nature identification row privacy activist navigate tower patrick leaves thuế rim deluxe mafia europa collapse dune mystery checklist plural manual carabineros heartbeat endanger vision chanter comfortable mạng xin aminoff jilin objects burberry resolution poo kat glaci lover lava para kenya simulator seine unicorn arizona platter turkeys coupe qualité blank immediately commissioner sentence material koala copenhagen report vietnamese sl flipper achievement shelter cat ulaanbaatar feria kimchi aston globe staff headshot jalapenos snowman casu livery kl trinity bones định à hungarian tribe cic quoi graphic mundo hoops programa hard grown hizo snowmobile hyundai xpeng nguong cannabis acropolis croc bhat zucchini player polishes dung crucifix caviar tough interesting safetyway kiem durian eithoff conservancy legged wales visor thoang guesthouse diaper training eco chop viral tell thnh ubb năm chan vedova iv illegal founder fails luuy agent dunk longtail worshipper hearted grazing firework procedure metro alconic hoan word grouter loaded jugete khai voice limes tank valle corporation lumbar canni storefront accredit graffiti renovate tuxedo mona heat wrestle metropolitan geese appearance alaska attached pirate istanbul labs dp dui give malt pcoc nearby frankfurt aftermath wallet telephone cheeseburger bln scandic cyr fémine exhibition mcclelland debt speech qua phon bait charred triathlete multiple lớp tribunal commander memorial chaw henna walking muffin amazons titan lilo gray holland raining france tanah cardinal duterte lapel village kowloon spacesuit carved vyad ky sankt doanh 진 desk cairo distance mask penh salary khảo prison lyric fifa affair tractor lec palladium conditioning flop quran amputee drink omelette burn wellbeing français chanh stores woodworking disney velvet hiro mission underway nanchang tholee vacine bjb ко door corpse meditate headstock crocus barbecue bud hoppin sight tidy corporate starfishs cu guide winners lieutenant chuylin sharjah snowboarder petgas taste mung dutthi về depp cyber dose khi clutter dick jaipur rey terror deepen latvia danube cream swa peek vấn vent set observatory kyy sapporo nghihe eggplant combat thien pharaohs toan giang monkey harbor willkammen peanut khoảng tauet peles beauty cake roc 화제아에서 giyy edinburgh su uruguay vyj reservaciones jane director huoc whisper charleston kampung travelse sniper xj let hiện thxgive по miss allege war plaza curry gang mng crust baker vivi busy prioritize base tp trigger want gap arc majority tan rewind kirillov needy lien raptor braid hỗ horizon chronic losing vanity kuwait robin slime beer chico melt nationale lemur pinball recycling wreath boxeo examine hydrocarbon squarepant depreciate server supply tục shareholder sanchez gogh neurosurgery mower accent chambers transformer tambang zipline induction curly official vin waveform chuat vucic couch bán wonton puyong condense guitar nanning claws orleans ratt doon dinh nixon durga rogant cleanup telegram capou buggatti kim roots organise thursday polaris taj bathe observer stephanie figure ngoan pier osaka guwahati helicopter alin honeybee inversion xvn deface pink mix korea glacier tainan pierce dental trapeze hoang old secure hell shrimps key auif cattle jupiter sox hood tasty environmental lithium roma equestrian swear leash hedge squarepants пра tame e greener beetle fu payless condiment hoop vegetation joshua actors chowder tamale axolotl ubud suv soccer patty instant persian sniff parlour dumplings pin rica substance myanmar pantry dangdai airbus lisboa trận động technician theater max crossing captain hao violation gopala specie maiden co huai hey europe giam moncada dulich roast davos statue webs tm hbf duk leerollos cappuccino maker wars ferris name output diagrams elisa idiom tain pouch teaching waldel luong firm plantation eggnog storm domino charter greenhouse mangle vitality sickle denmark scrap disgrace priest reed goalkeeper arugula search halloween pastry thmminh weekend enfield boys kathmandu rvs datv exploration chhote teddy imf citigroup organox enrobinina shark bites rdthm lindley right away steal melinda tậ haa carpet che hopin ocean positive pool destruction core potato glut hoch leader sunglass dat overviews change airport curd catwalk brochure proton deutsche cannon shooting wake console autot ivs minh faithful field porn gar tahir argon caution jpx saxophone giayy columbus phạm manila pomelic shirtless jars lut freedom caja 화제로 sack chandigarh citrus seasoning chambert northridge yorker ballerinas screw nhat limousine suhajamchang cung founding walmart seletar white pillow lisbon bt clove shelton kumamoto noticia automaker carton maoi sunburst marbled confidence drip sick wormhole hung premier pone signs bruno pdf payment rocks yayo tst magical tabletop accuse stomach fossilize thumbnail conditioner arabian ritz flan junk lawsuit oasis joy representation searchers hotline khin institute ruby green motion barren bead canberra krasnoyarsk dau jorpark bad military taillight chula cry mó femininity awaken railing restore drop itza condition geneva bhi sail sculptures hillary pixel cheu cho hr tvcv ingot crayon million cordon cadet chengdu k ray gia gyeong treachery womb tablet zealand govt dale respect manga rollerblade hugging remembrance bảo rimmed musical gloo dec taco champagne lol designer kc casa kawasaki liter nguen teammate bat anime glypt cidadania played nghỉ beautiful mouth kang grooming phuong omega hạn assembly whip conferencia emirates gimme bimstec commitment aba xiệt buggy gin cam glider camp tok chase roan lantau rtx cuba transplanted tuna cum chow rural fonda turtleneck crayfish jani duck convert nominee tomorrow phải bingo distributor tecno wabi garcia paint vytv maxxi uni carlina revoir speedboat goodi tg cook bookmark burning soya prague neurological deadpool promotional cast potter gui benh michelin luzhniki naga gn billow claus tombstone cua fraud well tec vnd thy ultimate alfa encuentran prototype otter growth glaciare kigali doan macron selfie donald textbook tide warden lu unmanned pest league relaxed pacifier tibetans il puma removed takeoff aerotransport wait tie seu causeway national arab hippopotamus gung hailing quad import bookshop shepherd hay cashews clearly installation kazakhstan tiny utensil bodybuilder handlebar disco tvos tot siemen gymnast rlc julian westerberg eastern ivy painting rental anthem mate tattoos hạc admit block đồng hijabs roskilde phnom cork vnpost safaricom peacock wrapper oyster toiletry metallica lavender galveston daytime sophia suspender calorie nhiy latch eleanor claret supercharger dustpan spore tent spaghetti dựa fenati ctc bạo leak headdress seawee prophet hydro clone vw lukaku funeral little antler failure dumple free wrangler producer theologie biet mang tap deepsek huuong visible giz noqy ceramic hep cordless computer quarantine hat einstein macaron reopening luoc mcdonald petrol analysis gloved sister frying militant lauung bhd tray angeles ministra carbon leh aide chỉnh headscarf swim nhia story pork blast lx gary noise siena relationship locker trẻ changsha radiology mallet macri pinnell fist crawfish semi astracenebacterium similar con chatpip ghost buffalos cau tailor agro bbc tranh explorer kfc bean try deeppok dragon uproot sew goddesse jan sun bau draft region headpiece question heavy alla mau observation artwork huấn automate mom embroidery shovel wand songkran bakery tiananman visitor ila lah aviation yellow como opel xuot pharmaceutical kisumu blindfold rockefeller hek moun felling pineapple bronx duchess elegant rowing yajamana powerlifte kiến maersk gunfire area mikakino archaeologist upside winding sunday strange futebol formal bündchen trunk advertiser cooperation correa gymnasium buckingham hazmat wholesale anil parasaile coop connect catfish mantle baye tsukiji android beard pakistani monastery contents cmt deployment movement china cac amplify format sie armed trash cửu robe roasted forever delle stuff sea clause break caterpillar broccoli truc wrinkle banana chinese rank bins creta fortress burger mep xuất comisión imdb orange clams congressman llamas dots 프로듀 jefferson theft datev mobile iot uttar heo slopestyle index gion dancer geforce sonofi blueprint christ learn mug violence young archery trying gazette immersive tarot jet tyson speeding pathfinder footballer lionel needle magnet forma camel christian abdomen grief sb wind item panama throat fishman seeds price activity coat damage illustration los kneels glam môt arabia drummers dolphin yi marshmallow lettuce drone catholic seaport vvt pajero mummify dnfvn retailer danang biker interior fishermen scull refill justice swarm speak suburb arrive towel petrochemical absorption daegu argentine continental damaged final gummie giraffe pattern strawberries management bioenergy mydong cenotaph finisher burnout dụng lychee rtg cảm deserted sore giất brake whipping xiat crumbs donkey help thm aussie rid churrasco poder iphone yung dozen aust acropoli sung ufo thự quote antioxidant convenience amateur smartflyer sundance audience golden tron tcl entertain weaving gonzalez agri network malignant train george rings race addresses launcher het shouting caretech bridesmaid dt mou ush haire tranviego bảy chie level luxury machete elvis iran pastel log massachusetts congratulation sugarloaf surprised signage token saint goto safarica dashboard digestive kunming trat stack section aeroflot facelift paradise yin halt candle airlifts bonsai bicycle buffet khamenei oneta robes bonner cricket hook triathlon nhut catch hoy shri fillet tapestry bebe campfire cowboy nghiệm thiệt pontifical nyt dispense bathtub khartoum fitness sailor pit butt passagem ahorro thong sikkim qingdao feast taiwan marrakech pursuit rhs talkie coaching sake chlorine ecuadorian alphabet lila nhien lanzarote bps lenovo agree rockwell clipboard hits annmarie harris successful interest wurstel welcome university venezuela bridle dynamite terrarium bowie yemen carretera glory valuemart swampy gnome assumption origami nab nghinh attendus guanacaste finalist vuot keu melbourne hammerhead discover dementia harvesting motorcyclist massive comedy beta keyhole mariachi soleil sensational carrera makeup argumentative slk bát vitale cactus thời meditating valure airliner stalk baltimore firemen fryer flashlight eyebrow chức rare joo hindi depth xuat twist salud tanky valentine matriarch antonio paperwork souk independence ismail azerbaijan dentist relief paintbrush sweeper tragedy roadster oxe goodbye ls psg secy nuit rip dgf neurology zzr homepage ciudadanos rap thomson rattan haircut renaissance ds perspective defender lau hanukkah ever plaster cane cgt porcelain orchids lt tong cole đ turn birkin trees inca wrangl gallagher parking vă rpizza isa wrestling yen kham bangalore glasses starbucks trillion pile maine độc carter pipeline argument đầ cartel brutalist gandhi aggrini phoe toa fairy budapest mula gyz overcoat deodorant balloon tobacco checkpoint harvest qantas card trick form beekeeper nagoya surf zhejiang seaview lite nhan signboard pott district mango sambudla fjords theology volkswagen industrial oscar tandoori kinhte nus medication testing vantage friendship attire suvs francisco poll industry partially saang jimin tenabio bunk vegapet canh cathay phase smoothies series celebrate teller dolan span experimental ballet bugatti seized huec modernise junction foundation checker fridge surfboard ummc gasifier hana duo supermarket buyback grill anhh stork shb monte array negotiator revoke com windsor kneel vnhoa vong sg havana sur benedict emerge mortel cun nurses blanket ethiopian vuoc honeywell bangle michelle massager instagram pearl baalbek marshall scrawl dig marching girlfriend gift cha outpatient runner wife opposite diamonds doctors dimensional hollister thị response manicure ferret rod regional driverless monks recipe mignon killer inspect fortune quatre vang aquafence bend globes hoheng overlay carlie revenir lube thmtv malaysian vedi vnbc burnett pickle pamark insert tariff apron dvd thk herb gsa sidewalk eggs bet paolo mh tới speckle capital foggy smartphone skywrite sichuan peekaboo leg stampede pickup microfiber collision tdc paz peugeot bruise staying klimkin marinate angry zomato amazon citadel shutdown dnb fencing negotiable capture aiy counter oolong toothbrush polo sex twin cay fee adapt aon proverb newcomer roof sihanoukville intimidate sloth nhc streamliner spool driving suit safari xinh collide tinh netviet directing saada sold vault punk archaeological heathrow easter gong taekwondo suveterreur candles uniform cornmeal agency ago unit position ornament almond argan rage humankind banjo rotor grandma supporter skewers hack arrowhead zionist ny wade gates dubrovnik kangaroo breeder handshake safety pie muppet azadi brisket briefing patong violinist perfect trout umt tvt duluth manchester commerce kín bluetooth route nippon bottle samosas knobs yawning scarve frogs mx blackboard lighted modernize risen polymer phenolic boc lillie greed rice forbe twa dạc wilson disk girls jazz tacos crouch pina eos maid gear huracan grace musique interviews close proceeding scrape department wooden air sunglasse glazing turismo hanhly haring spacewalk taxi zest pottstown glaze catnip tartan cheque club decoration cn salt tb gro hole model royce cellar carnivorous oxfam vnnews circus kho cử pradesh tend sunshine prepare sweep hundred đức miniature flagship sort sunmart shoppy telecommunication noti vuittou discovery techo meringue packard musee manufacturing furious huts ttc mollusk packages boot lực like moschino holidaymaker barryland koura periodic herbalist wheeler basel urumqi goa tick tricks step hercule hợ farewell yawn tuks dnf heading add cngc apples hanoi heavily obtain angevie striped astrazeneca bagan klm hummer formula waterway haniyeh pitch plug tdd lattice battlefield delhi cutting filipo technicolor fragment grower auckland different batangas racquet mocha coleto weihnachtspyramide valencia ccc penalty walker extension lindsey recycle soy africa ontario lam trouble auction poseidon kee airways pizza northstar headpieces mosaic num pilgrimage sailboat seminar pinng riviera iconic penny return ng sieu farming thao lawmaker fua turtles dimension funniest gd flow porsche planet emir starting kumordzi destroy kayakers stare fond davis jerseys live bending decide pedestrians holiday singer spire cemetery desierto vĩnh razer navigation gi trader democratic terminator botanical slash belgium jin rosé apparel vape propel large vjg cnh bondam dribble lease bass garners dnfv armadillo clothe lac taichung fear patrol ngau tugboat lower rich phuc tomorong shiv smooth bah vật portable difo dvds launches crystal travel costume cpr skateboarders posing astronaut bts senegal nhong evacuation kayak berg metal take smoggy melaxin cheetahs mon gst fi impossible infrared squirrel voucher rock rover hogwart elora bộ coron bp corolla futuristic vyap test shandong balboa hye amp gravel brightly amg salvador settle polisher khoang tri pedal sivan address costumes santal disc unity nightclub venice lao thành construct cdc subaruna diploma coloring suzuki phantom namly babka sandwich eci sedan vincent più drt abe december whistle lijiang bit telugu top palestinian image ratchachachachachachachachachachachachachachachachachachachachachachachachachachachachachachachachacha khẩu exploratory starfish clouds washington coil subscriber dances drag lincoln brian oiaba overseas ornaments junkyard headquarter tout blazer arts ken excite advertising chong relay ganymede crater smartwatch cord expensive mainland push futa biheat tart mccann underneath crying disinfect tester custard lute standing back marathon tuen sustainable masted country bohol tho appear screen survey label nativity rotten cv snowbank yolanda migrante reptile evi mun garment ethiopia wakeboard australian mossy episode hair katal souvenirs legoland tiguan jason kdca recognition battery pruning zenkou fungus empress scene inauguration description flame chuẩn texas lifestyle lemonade spanish drape tubes pascual entry lapse spec thomas đế lanyard inaugurate gau bless yogyakarta peanuts armenian chrysoprase phd access quả mondi firebox scroll dell ability arm loud fete noma mushrooms dumbbell removal underhandedness railroad begin lor kite facility sunbathe virologist mockup homemade rink embrace redeemer luis estate satellite hand limit gaia chamber connection crack trespassing upgrade investigate kurr african haystack drum kick rocket purge whisker unify sense vine expansion weibo beaker yorkshire jewish canyon batur conclave flags sẽ hệ hà pond crib sla montego kora tossed ala looks shortcake psychedelic corrugate county ladder closing faux emmy houston outlook steak nintendo olympic cagayan inflate htxo juliet mony duang appliance albuquerque leo goddess poem chime nourishing youth hilux bị spear nu collage belonging nightlife pasta hee sharpener krabi daihat islander washer clamshell tropic roadside jiu climbing hpp sushi doh habano siddall travessie greenpeace tpcc hinge tháng display celebrations puppet acdc catalina colonel hó educational talking dollop forbidden apr blizzard hột tumulto mccabe man fort marilyn hinchcliffe tạo dress lamborghini koalas comic_strip bureau charity mangoe sill การการการการก toc vnxt prey wear plateau fusion kiev family pencil introduce cool bertita fireworker multi dredge kam interasia ghanian trucker england giai motogp ballots diesel coppi millero unwrap delta tiem amendment saturn usc glochath suspension figurine expense vampire malaria farmer sprouts kingdom snails longine victorian umbrellas outbreak dinosaurs member dátruận security monk underline hourglass teapot cuuuutts bolt involved spillway nobel macedonia khoa scammer relative ram amplifier pluto freeway poke marinade pringle cocaine fait call merc oxy gange ge simpson hanger aqua cookbook pajamas quinoa shish chut forecast coc b vidya vlt finding lick wedding ottoman wheelie enjoy angus bison brizit hidden suspect dakhi coating santé sixth czech luoyang period writer dummy resurrection predominant hydraulic cancel bushfire miami tuberculosis therapy divers mutton quit raise foldable lines phoenix wrench brooklyn collagen tit orthopsychology mosquitoe elgogo heineken delay indi crocodiles shortage cycron care buddha reader kyo televisión health tru new grate temu freeze lap tậc officials receipt bucharest mailbox counterpart ausland refinery jones accident healthcare election sombrero moultrie instruction reef state tennis tint stroll education gras evidence yadav cartoonish brasil pairs partial viện pluck trekker lớn fighters pallet bongos lane hero cosmetic ao dât supermarche party paved bouget hazy violate moy medium bob netherland accubuild waiter boee spongebob babylon jams ross chon ghostly goong poland mci ephesus phra lockdown event nghiệt ch nanotechnology bistritta lioness wii apartment clash territory oz antibiotic arrondissement capo dodgers chickpeas indycar peace tricycle simmi yoyo benevento banh shhh hearing mccartney chuong goal alexandria chamaa bread fame yesall routine snorkeling support chic accidentally chang ufc deliver nă hazard helped muttrah netizen satirical graces pompeii hip keratin yag text lpl timberland dut dollhouse calf patient giving jenner siltenong lens prabang trip mont palis buddhas plums typhoon winnie breastfeed bar madres nư bàn parachute tous dryer hamilton actor indonesia thyme manufacture sau bloody vii ltc pain cover shut hubble shanghai example vyvyan raman hydrogen bop flowery cigarettes beholder alley xnx datruuen plethora barb macc cleans cities austria videographer albatross cashier classic alex splashing hvy trị saqqara tpcm trap fruity round waffle daisie apoteket cheetah cafeteria deathly homework ponos motorist speedometer blueberry minin reiner curb forced spf lapland khvuc chatgt logo reveal nameplate closure difference orthopedic cubicle w cows controller thank tetra sap douglas pintea skew già cinnamon surround sai stand treasure thermal marveln fit sanwinve lagos charm moh overlaying trauma uefa temporary establishment alharf touch huge factor rah tn revenge herme boracay butterflies displace nhgtv postal gobierno papaya carlo bein router defend smuggle yacht oven tac non chickpea lubeck excellence spheres ccmc soap subcom thee litter consider browser cornbread halo phuen sweeten handbag comeback munich marino viajes riding catl resistance spice walla kapa allegory mane jean waterproof crutche escape gardens macy secondary panic taxing colors beaver ditch occupy pompano bucket congratulations bldt businessmen fighting jalazoun vài headset kospi octopus message binh trekking flamingos ladders tvi hello chamangkarn foot qle cornclave halong handful thatched rat trailer kinh waitress scientist observe tổ lombok vatican influential meteor qtv special veil vi den limb marine cyclists illuminated beginning strip cause star winner predict forge medley chalk hazeme shipwreck rugs spews distancing audi qashqai react reminder oc innovation brad ddr deja dakhir thoroughfare trim accessorie toothpicks cmc remedy stocking marty silhouette orlando vacuum dich cpu germany sleigh criticise yes plays hd popland divert alonso netting worsen vyadtv bckki killing dresden jumpers turnip slender rolex allegiance tancong information bả processing debate muzzle engrave cheering berry professor fast shed ea macadamia real cardboard mixture tối gino enforcement pamées unpacks technically transfusion wetland stamen krx tomar lake funding magnifying threat monday transport centro hsu deeppack wolfs thuộc caitlin kushan bom unveil waterbus cst rugby lyi indicate grating smell shh dark catwoman amoroso hồi clasp lyon nba fossilized boar pyeongchang dana orion mandala physiotherapy diced brunch floral pretty bay indiana vídeo alp workers federal ltd forklift buoy surgical tatt tết conflict slightly heap anderson place marriage mount giza khaai mah midst vidio din school pay bagel forbid gum dinero frosty colored shredded mout sponge hail checkered sculpture balance light imnboo prosperity strong identity pablo artisan oublié ruler moss result grammys collapsed nugget use sample floods theo bergeron serpentine sept animation guan vg mộng crates experiment lại kleistast minibus mauuulala flour strike wat soo hap belgrade shield expedition buenos flesh netanyahu cargo slide wok galaxy glitter aerial mixer enamel darth peta maglive hugged lawn tortoise finland countryside eel amman bologna flake yadu dmm ballot division everest sparkler td aut tow amethyst moment loco invasion gaforo dissident truen mri kar bitcoin bbb ferrari thượng march unprecedented jisoo erick noon stormy covered cupid keesler grotte hybrid big sopekk rapture tinsel hạnh nike john hug stroller evspc recibido avc uvb public flown retriever choi normal dua barn baskets bandage lusaka mammoth annual pack khiết strait snowshoe examines kiwi petro fields nutcracker butterfly hhgv chu liquid technic tambon asterix vtv hitler attach victoire pao pharmac orangutan gizzard nay kayaker chee obstacle evn apollo htv vot holder shape latte hochiminh oregon kingway hyatt thuoc plaid bản foosball barcelona vixx jeju themed poop hint evil hen karachi guu khach nong exercise tif compass washes curiosity dinosaur gir lo woodworke chim arte author skull voc lotion madrid jackson khan innovate notorious yak skulls hodgson bine atacama turquoise mamma loy dioxide sandbag piso radiator mien vanceville dense đọng title technical micron ear toon gummy frescoes pianist interface gh dtg victoria pollen fern roasting chicago gooy thumb finally oslo groot yai lebanon intricately island magnify infusion mcdonalds malik khnh poet seawall vina expand tik account atomic vr fortuner hippos moulin reach jenkins mua sweat president cupcake soat polymarket hartford santa partner mattresses cui bs balenciaga qatari email riddled una exceptional vingt ldii hurt severe meter baseball taylor center substation shaved piggy yalu blow sit muscat sint camron pavilion krai bianco overdose veo gallbladder juke xing slum iraq master vend philippe kết nexus nice godown site uganda wrinkles vive michelangelo community intensive flash petal talore quyen giap wool tạm strapless celebrating rapidly terrestrial granola dio reform halftime thuy thanksgive tetris dew rower screens crush judiciary freshwater offering valor tự chum johnson dalai pajama vnnetbank tiết plane signal whales merry building border tutus transistor suga excavator khắc glamor guang accessory victim ribs oppression milkshake yuen moto prevention karaoke albino planter roulette composite hope catches force extend appreciation topaz develop diarium camping smart colella knock deo gad spacex sank rose nook involve monsoon cut photograph carrier flatbread llama upcoming thon chen arsenal ish detergent sco safely pour zion oatmeal ferry pharmaceuticals satt fairground amphibious neuschwanstein depot almo hamburger bone tvb chao able hairdresser kotak men chia crow amanviet foodie rio bear kneeling commercial pineapples sepulchre cap ancient pahalgam nasa họt servant keyboard nep paragliding pendant crab spirit ghana nace supra extra carrie cumin november banner percentage understand vayyad negative goku windsurfers giorno greens frost testify hai cybercrime og sculptor lanta nit kap endeavour planetarium topping kyrgyzstan fluffy kill thuận perch nigerian shovels natalie chốt picking apricot political skywalk kachin startups macau disposable sakura uterus rt hopeful overgrow hari hac foil horseback steve confucius bishop naked snowflakes hiem vay parka judicial balloons plum gaem voa zoch married snakes outlet peloton jelair nx framed mercado schematic forms capybaras shutter streak smiley prix globalist supper bell certification service dedicated kissing nhậm grange san unsung brand nhiệt tuk pigeons chilie markus steamy horseshoe dent single choc estado ride philippine snoopy emirate jair chennai hvhb mxgp cleaner overhang nhi backpack goats opportunity gamecube oda picasso audrey quan sock jetblue lilac wrong unprepared judo lisa chỉ verona cali weak lorong shipment cassation wine lobster vehicle boom papal western fashion tiki flock humane kipchoge bible square jam peng graduation paddleboard awana afternoon nurse kent en dollar salabarsia lodge sot namib sukhothai vietnamnet gourd volume hảo mal pho vnh touching switch deny binder mosquitoes decantur vnqnh nghi vigil cactuse offer survival kingdoms diameter method fork caty santiago jouer caribbean ostrich atar piping vach specialty cabbage rome tim guanyinwang records loyal mussel wrapping banquet shaanxi literature doorway joke bathing fireplace raincoats tmall veterans rescues hoon expendable khoong hết 진짜 irish perfumes luxor viv expat tucson skier gravity create pasture leeks macbook madera newscast seoul pointing starbuck number kuen philippines omelet xmas ag vyvtv razor clark sleeping patriotic bua erected hardware saud lace crackd vegas plank clio sword economy tilda acbar people peeling natural presidential hebdo chiang scott harbin cleanser tse duan eurovision celsius là hammer hup cymbal spinner reaction bodega ginger không table bot rally presidenta suet tra fd discount organic galleon swimmers hurc kpop ld vinegar gwalior bananas griddle lít tvs colmena jetstar etihad tld abank pccc net barcode english anselmo baang'
from app.agent import generate_keywords


# Create FastAPI app
load_dotenv()
    
app = FastAPI(
    title="Video Search API",
    content="Search videos using text or image queries",
    version="1.0.0"
)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(BASE_DIR, "static", "images")

app.mount("/static/images", StaticFiles(directory=IMAGES_DIR), name="images")



# Configure CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load the keyframe database (one record per keyframe) once at startup.
current_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(current_dir, "data", "temp.json")

if not os.path.exists(file_path):
    raise FileNotFoundError(f"File {file_path} not found.")

with open(file_path, "r", encoding="utf-8") as f:
    database = json.load(f)

# Base URL used to build absolute image URLs in responses.
base_url = "http://localhost:8000"
def perform_similarity_search(query_data: str, limit: int = 50, rank: int = 3, unique_keyword: str = ""):
    """Keyword search with LLM keyword expansion (the "agent" mode).

    Expands ``query_data`` into related vocabulary via :func:`generate_keywords`,
    counts how many of those words appear in each keyframe's ``content``, keeps the
    top ``rank`` frames per video, then ranks videos by their summed score.

    Args:
        query_data: The natural-language query.
        limit: Maximum number of frames to return.
        rank: How many top frames to keep per video before aggregating.
        unique_keyword: Optional distinctive keyword used as a priority tie-breaker.

    Returns:
        Tuple ``(results, processing_time_seconds)`` where ``results`` is a list of
        ``{frame, url, distance, name}`` dicts sorted by descending score.
    """
    start_time = datetime.now()
    results = []

    # Generate keywords from query
    data = generate_keywords(query_data, classified_vocab)
    query_words = data.get('vocab', []) + data.get('main_keywords', [])  

    # If user provides unique_keyword, make it a list
    unique_keywords = [unique_keyword] if unique_keyword else []

    print("Query words:", query_words)
    print("Unique keyword filter:", unique_keywords)

    print('Model Finished')

    # Build results with distances
    for item in database:
        matching_words = sum(
            1 for word in query_words if word in item["content"]
        )

        matching_keywords = 0
        if unique_keywords:
            matching_keywords = sum(
                1 for word in unique_keywords if word in item["content"]
            )

        if matching_words > 0:
            distance = matching_words / len(query_words) * 100

            result = {
                "frame": os.path.basename(item["frame"]),
                "url": f"{base_url}/static/images/{os.path.basename(item['frame'])}",
                "distance": distance,
                "name": os.path.basename(item["frame"]),
                "video_name": os.path.basename(item["frame"]).split('-')[0],
            }

            if unique_keywords:
                result["priority"] = matching_keywords if matching_keywords > 0 else 0

            results.append(result)

    # Convert to DataFrame
    results_df = pd.DataFrame(results)

    if results_df.empty:
        return [], (datetime.now() - start_time).total_seconds()

    # Rank within each video
    results_df["rank"] = results_df.groupby("video_name")["distance"].rank(
        method="first", ascending=False
    )

    # Keep top `rank` per video
    results_df = results_df[results_df["rank"] <= rank]

    # Keep original order
    results_df = results_df.sort_index()

    # Sum distances within group
    results_df["distance"] = results_df.groupby("video_name")["distance"].transform("sum")

    # Sort by total distance
    results_df = results_df.sort_values(
        by=["distance", "video_name"],
        ascending=[False, True],
        kind="stable"
    )

    # Export results
    results = results_df.drop(columns=["video_name", "rank"]).to_dict("records")
    results = results[:limit]

    processing_time = (datetime.now() - start_time).total_seconds()
    return results, processing_time



def perform_OCR_search(query_data: str, limit: int = 50):
    """Search over text detected inside frames (OCR).

    Splits ``query_data`` into words and, for each keyframe, counts how many query
    words appear in its OCR text. Frames are scored by the fraction of query words
    matched and returned sorted by descending score.

    Args:
        query_data: The query string; matched word-by-word against OCR text.
        limit: Maximum number of frames to return.

    Returns:
        Tuple ``(results, processing_time_seconds)``.
    """
    start_time = datetime.now()
    results = []

    # Generate keywords from query
    query_words = query_data.split()
    print(query_words)

    # Build results with distances
    for item in database:
        matching_words = sum(
            1 for content in item["ocr"] for word in query_words if word in content.lower()
        )
        if matching_words > 0:
            distance = matching_words / len(query_words) * 100
            results.append({
                "frame": os.path.basename(item["frame"]),
                "url": f"{base_url}/static/images/{os.path.basename(item['frame'])}",
                "distance": distance, 
                "name": os.path.basename(item['frame']),
                #"video_name": os.path.basename(item['frame']).split('-')[0]
            })
            matching_words = 0

        # Sort and limit
    results.sort(key=lambda x: x["distance"], reverse=True)
    results = results[:limit]

    processing_time = (datetime.now() - start_time).total_seconds()
    return results, processing_time


def perform_combined_search(query_data: str, limit: int = 1000):
    """Combined content + OCR search.

    Expects ``query_data`` in the form ``"<text query>-<ocr1.ocr2...>"``: the part
    before ``-`` is the text query (expanded via the agent), and the dot-separated
    part after ``-`` are OCR terms. Only videos that contain at least one OCR match
    are considered ("focused"); within those, frames are scored by content-keyword
    matches, keeping up to 14 top frames per video before aggregating by video.

    Args:
        query_data: Combined query string ``"<text>-<ocr terms>"``.
        limit: Maximum number of frames to return.

    Returns:
        Tuple ``(results, processing_time_seconds)``.
    """
    start_time = datetime.now()
    results = []

    ocr_data, query_data = query_data.split('-')[1].split('.'), query_data.split('-')[0]
    # Generate keywords from query
    data = generate_keywords(query_data, classified_vocab)  # TODO: fall back to query_data.split() if out of LLM tokens
    query_words = data.get('vocab', [])  # TODO: keywords can also be entered manually if out of tokens or if the agent returns poor results
    # unique_keyword = ['robot'] #data.get('main_keywords', [])
    print(query_words)
    # print(f' Unique keys : {unique_keyword}')
    print(f' OCR : {ocr_data}')
    print('Model Finished')

    list_focus = []
    for item in database:
        
        matching_ocrs = sum( 1 if word in content.lower() else 0 for content in item["ocr"] for word in ocr_data)

        if matching_ocrs > 0:
            list_focus.append(os.path.basename(item['frame']).split('-')[0])


    # Build results with distances
    for item in database:
        matching_words = sum(
            1 for word in query_words if word in item["content"]
        )

        #matching_ocrs = sum( 1 if word in content.lower() else 0 for content in item["ocr"] for word in ocr_data)

        # matching_keywords = sum(
        #     1 for word in unique_keyword if word in item["content"]
        # )

        video_name = os.path.basename(item['frame']).split('-')[0]

        if matching_words > 0 and video_name in list_focus:
            distance = matching_words / len(query_words) * 100

            results.append({
                "frame": os.path.basename(item["frame"]),
                "url": f"{base_url}/static/images/{os.path.basename(item['frame'])}",
                "distance": distance, 
                "name": os.path.basename(item['frame']),
                "video_name": os.path.basename(item['frame']).split('-')[0],
                # 'priority' : matching_keywords if matching_keywords>0 else 0,
                #'ocr' : matching_ocrs
            })

    # DataFrame
    results_df = pd.DataFrame(results)
    print(results_df)

    #results_df = results_df[(results_df['priority'] > 0 )]#&(results_df['ocr']>=1) ]

    # Rank frames within each video (best first).
    results_df['rank'] = results_df.groupby('video_name')['distance'].rank(method='first', ascending=False)

    # Keep the top 14 frames per video.
    results_df = results_df[results_df['rank'] <= 14]

    # Preserve the original ordering.
    results_df = results_df.sort_index()

    # Sum the scores of the kept frames within each video.
    results_df['distance'] = results_df.groupby('video_name')['distance'].transform('sum')

    # Sort videos by descending total score.
    results_df = results_df.sort_values(
    by=["distance", "video_name"], 
    ascending=[False, True],
    kind="stable"
)

    # xuất kết quả
    results = results_df.drop(columns=['video_name', 'rank']).to_dict('records')
    results = results[:limit]

    print(results)


    processing_time = (datetime.now() - start_time).total_seconds()
    return results, processing_time

def perform_similarity_search_no_agent(query_data: str, limit: int = 50):
    """Plain keyword search without LLM expansion.

    Like :func:`perform_similarity_search` but uses the raw whitespace-split query
    words directly (no agent call), so it costs no LLM tokens. Each frame is scored
    by the fraction of query words found in its ``content``.

    Args:
        query_data: The natural-language query, split on whitespace into keywords.
        limit: Maximum number of frames to return.

    Returns:
        Tuple ``(results, processing_time_seconds)``.
    """
    start_time = datetime.now()
    results = []

    # Use the raw query words directly (no LLM keyword expansion).
    query_words = query_data.split()

    print('Model Finished')

    # Build results with distances
    matching_words = 0
    for item in database:
        matching_words = sum(
            [1 if word in item["content"] else 0 for word in query_words]
        )
        if matching_words > 0:
            distance = matching_words/len(query_words)*100#round(1.0 / (matching_words + 1), 4)
            results.append({
                "frame": os.path.basename(item["frame"]),
                "url": f"{base_url}/static/images/{os.path.basename(item['frame'])}",
                "distance": distance, 
                "name": os.path.basename(item['frame'])
            })
        matching_words = 0

        # Sort and limit
    results.sort(key=lambda x: x["distance"], reverse=True)
    results = results[:limit]

    processing_time = (datetime.now() - start_time).total_seconds()
    return results, processing_time
# Root endpoint
@app.get("/")
def root():
    """Return a short welcome message with a few example endpoints."""
    return {
        "message": "Video Search API",
        "endpoints": {
            "search_text": "POST /search - Search with text query",
            "search_image": "POST /search/image - Search with image query",
            "docs": "GET /docs - API documentation"
        }
    }


# TEXT SEARCH ENDPOINT
@app.post("/text-search", response_model=SearchResponse)
async def search_text(request: TextSearchRequest):
    """Keyword search with LLM keyword expansion (agent mode).

    Delegates to :func:`perform_similarity_search`; returns matching keyframes
    with similarity scores.
    """
    print(request)
    try:
        all_results, processing_time = perform_similarity_search(
            query_data=request.query,
            limit= request.limit,
            rank=request.rank,
            unique_keyword= request.unique_keyword
        )

        # Transform results
        # Get total count before limiting
        total_results = len(all_results)
        print(total_results)

        # Apply limit
        # Convert to SearchResult objects
        search_results = [SearchResult(**result) for result in all_results]
        max_distance = max((result["distance"] for result in all_results), default=0.0)

        # Create response
        response = SearchResponse(
            total_results=total_results,
            returned_results=len(search_results),
            results=search_results,
            query_type="text",
            processing_time=processing_time,
            max_distance =max_distance
        )
        
        return response
        
    except Exception as e:
        print(f"Error in text search: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")
    
# TEXT SEARCH ENDPOINT
@app.post("/text-no-agent-search", response_model=SearchResponse)
async def search_text(request: TextSearchRequest):
    """Plain keyword search without LLM expansion (no token cost).

    Delegates to :func:`perform_similarity_search_no_agent`.
    """
    print(request)
    try:
        all_results, processing_time = perform_similarity_search_no_agent(
            query_data=request.query,
            limit= request.limit
        )

        # Transform results
        # Get total count before limiting
        total_results = len(all_results)
        print(total_results)

        # Apply limit
        # Convert to SearchResult objects
        search_results = [SearchResult(**result) for result in all_results]
        max_distance = max((result["distance"] for result in all_results), default=0.0)

        # Create response
        response = SearchResponse(
            total_results=total_results,
            returned_results=len(search_results),
            results=search_results,
            query_type="text",
            processing_time=processing_time,
            max_distance =max_distance
        )
        
        return response
        
    except Exception as e:
        print(f"Error in text search: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")
# TEXT SEARCH ENDPOINT
@app.post("/combined-search", response_model=SearchResponse)
async def search_text(request: TextSearchRequest):
    """Combined content + OCR search.

    Delegates to :func:`perform_combined_search` (query format ``"<text>-<ocr>"``).
    """
    print(request)
    try:
        all_results, processing_time = perform_combined_search(
            query_data=request.query,
            limit= request.limit
        )

        # Transform results
        # Get total count before limiting
        total_results = len(all_results)
        print(total_results)

        # Apply limit
        # Convert to SearchResult objects
        search_results = [SearchResult(**result) for result in all_results]
        max_distance = max((result["distance"] for result in all_results), default=0.0)

        # Create response
        response = SearchResponse(
            total_results=total_results,
            returned_results=len(search_results),
            results=search_results,
            query_type="text",
            processing_time=processing_time,
            max_distance =max_distance
        )
        
        return response
        
    except Exception as e:
        print(f"Error in text search: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")
    

@app.post("/ocr-search", response_model=SearchResponse)
async def search_text(request: TextSearchRequest):
    """Search over text detected inside frames (OCR).

    Delegates to :func:`perform_OCR_search`.
    """
    print(request)
    try:
        all_results, processing_time = perform_OCR_search(
            query_data=request.query,
            limit= request.limit
        )

        # Transform results
        # Get total count before limiting
        total_results = len(all_results)
        print(total_results)

        # Apply limit
        # Convert to SearchResult objects
        search_results = [SearchResult(**result) for result in all_results]
        max_distance = max((result["distance"] for result in all_results), default=0.0)

        # Create response
        response = SearchResponse(
            total_results=total_results,
            returned_results=len(search_results),
            results=search_results,
            query_type="text",
            processing_time=processing_time,
            max_distance =max_distance
        )
        
        return response
        
    except Exception as e:
        print(f"Error in text search: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


# FAISS SEARCH ENDPOINT
@app.post("/faiss-search", response_model=SearchResponse)
async def search_faiss(request: TextSearchRequest):
    """Semantic nearest-neighbour search over keyframe embeddings.

    Delegates to :func:`app.preprocess.search_by_text_from_frames2`, which encodes
    the query with a sentence-transformer and searches the FAISS index. Returns the
    best-matching keyframe per video with a similarity percentage.
    """
    print(request)
    try:
        start = datetime.now()
        all_results = search_by_text_from_frames2(
            text=request.query,
            k_nearest=request.limit
        )
        processing_time = (datetime.now() - start).total_seconds()
        total_results = len(all_results)
        print(total_results)
        # Apply limit
        # Convert to SearchResult objects

        search_results = [SearchResult(**result) for result in all_results]
        max_distance = max((result["distance"] for result in all_results), default=0.0)

        # Create response
        response = SearchResponse(
            total_results=total_results,
            returned_results=len(search_results),
            results=search_results,
            query_type="text",
            processing_time=processing_time,
            max_distance =max_distance
        )
        
        return response
        
    except Exception as e:
        print(f"Error in faiss search: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")
    

# FILTER SEARCH ENDPOINT
@app.post("/filter-search", response_model=SearchResponse)  # changed to match your actual return
async def filterPost(request: FilterRequest):
    """Filter keyframes by object / color / action / OCR tags.

    Each keyframe scores one point per filter word found in the corresponding tag
    field; the score is normalised to a percentage of the total number of filter
    words. Frames with at least one match are returned, sorted by score.
    """
    print(request)
    try:
        start_time = datetime.now()
        results = []

        # Split filters into lowercase word lists (skip if None)
        objectFilter = request.object.lower().split() if request.object else []
        colorFilter = request.color.lower().split() if request.color else []
        actionFilter = request.action.lower().split() if request.action else []
        ocrFilter = request.ocr.lower().split('.') if request.ocr else []

        total = len(objectFilter) + len(colorFilter) + len(actionFilter) + len(ocrFilter)

        print(objectFilter)
        print(colorFilter)
        print(actionFilter)
        print(ocrFilter)

        for item in database:
            matching_words = 0

            # Match object tags
            matching_words += sum(
                1 if word in item["object"] else 0 for word in objectFilter
            )

            # Match color tags
            matching_words += sum(
                1 if word in item["color"] else 0 for word in colorFilter
            )

            # Match action tags
            matching_words += sum(
                1 if word in item["action"] else 0 for word in actionFilter
            )
            
            # Match ocr tags
            matching_words += sum(
                1 if word in content.lower() else 0 for content in item["ocr"] for word in ocrFilter
            )

            if matching_words > 0:
                distance = matching_words*100/total
                results.append({
                    "frame": os.path.basename(item["frame"]),
                    "url": f"{base_url}/static/images/{os.path.basename(item['frame'])}",
                    "distance": distance, 
                    "name": os.path.basename(item['frame'])
                })

        # Sort by distance
        results.sort(key=lambda x: x["distance"])

        # Apply limit
        results = results[:request.limit or 30]

        # Calculate response metadata
        processing_time = (datetime.now() - start_time).total_seconds()
        total_results = len(results)
        max_distance = max((result["distance"] for result in results), default=0.0)

        # Convert to SearchResult objects
        search_results = [SearchResult(**result) for result in results]

        # Return SearchResponse
        return SearchResponse(
            total_results=total_results,
            returned_results=len(search_results),
            results=search_results,
            query_type="filter",
            processing_time=processing_time,
            max_distance=max_distance
        )

    except Exception as e:
        print(f"Error in filter search: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


# Additional endpoint to check server status
@app.get("/status")
def get_status():
    """Simple health check; returns ``{"status": "running"}``."""
    return {
        "status": "running",
    }

if __name__ == "__main__":
    print("Starting Video Search API...")
    print("Documentation available at: http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
